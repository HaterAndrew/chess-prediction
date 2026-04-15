"""
Scrape historical CCA tournament data from chessaction.com.

Fetches all completed tournaments (~720) via the CCA AJAX endpoint, then
enriches each with entry list HTML and real-time count data where available.

Outputs: output/historical_tournaments.csv

Data sources:
  1. POST /tournaments/ajaxFrontGetCompletedTourListForAllNew.php
     -> JSON list of all completed CCA tournaments
  2. GET /tournaments/advlists/CCA/CCA_{CODE}{YY}/CCA_{CODE}{YY}_alp_n.html
     -> HTML entry list with player details, sections, ratings
  3. GET /tournaments/ajax_get_adv_params.php?tid={id}&met=0
     -> Pipe-delimited: total|status|registered|ref_id

Usage:
  python scrape_historical.py
  python scrape_historical.py --limit 50   # test with first 50 tournaments
"""

import os
import re
import csv
import json
import time
import argparse
import statistics
from datetime import datetime
from collections import Counter

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scraper_utils import polite_session, rate_limit as _rate_limit, DEFAULT_TIMEOUT

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "https://www.chessaction.com"
COMPLETED_URL = f"{BASE_URL}/ajaxFrontGetCompletedTourListForAllNew.php"
ENTRY_LIST_TEMPLATE = f"{BASE_URL}/tournaments/advlists/CCA/CCA_{{code}}{{yy}}/CCA_{{code}}{{yy}}_alp_n.html"
REALTIME_URL = f"{BASE_URL}/tournaments/ajax_get_adv_params.php"

# ── Tournament code mapping ──────────────────────────────────────────────
# CCA uses short codes in their entry list URLs. This maps known tournament
# name fragments to their URL codes. Not exhaustive — unknown tournaments
# get a best-guess derivation from their name.
KNOWN_CODES = {
    "world open": "WO",
    "chicago open": "CO",
    "national chess congress": "NCC",
    "north american open": "NAO",
    "liberty bell open": "LBO",
    "atlantic open": "AO",
    "atlantic city open": "ACO",
    "new york open": "NYO",
    "new york international": "NYI",
    "amateur team east": "ATE",
    "amateur team": "ATE",
    "mid-america open": "MAO",
    "mid america open": "MAO",
    "golden state open": "GSO",
    "pacific coast open": "PCO",
    "pittsburgh open": "PIT",
    "cleveland open": "CLEV",
    "chicago class": "CC",
    "george washington open": "GWO",
    "philadelphia open": "PHO",
    "eastern open": "EO",
    "national open": "NO",
    "las vegas open": "LVO",
    "western class": "WC",
    "los angeles open": "LAO",
    "national k-12": "NK12",
    "king of the hill": "KOH",
    "empire chess": "EC",
    "new jersey open": "NJO",
    "marshall chess": "MC",
    "bradley open": "BRAD",
    "dc international": "DCI",
    "dc open": "DCO",
    "hartford open": "HO",
    "new york state championship": "NYSC",
    "new york state open": "NYSO",
    "southern open": "SO",
    "central california open": "CCO",
    "southwest class": "SWC",
    "boston chess congress": "BCC",
}


def create_session():
    """Create a requests session with polite headers and retry logic."""
    session = polite_session()
    # CCA AJAX endpoints need these extra headers
    session.headers.update({
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.chessaction.com/tournaments/",
        "Origin": "https://www.chessaction.com",
    })
    return session


def fetch_completed_tournaments(session):
    """POST to CCA API to get JSON of all completed tournaments."""
    print("Fetching completed tournament list from CCA...")
    _rate_limit()
    resp = session.post(
        COMPLETED_URL,
        data={"vendor_search": "3", "length": "-1"},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()

    data = resp.json()

    # The response may be a dict with a "data" key or a bare list
    if isinstance(data, dict):
        tournaments = data.get("data", data.get("aaData", []))
    elif isinstance(data, list):
        tournaments = data
    else:
        raise ValueError(f"Unexpected response type: {type(data)}")

    print(f"  Received {len(tournaments)} completed tournaments")
    return tournaments


def parse_tournament_record(record):
    """
    Parse a single tournament record from the AJAX response.

    CCA returns dicts with a single 'html' key containing embedded HTML.
    We extract: name, tid, start_date, end_date, state.
    """
    info = {}

    # CCA format: dict with 'html' key containing full HTML block
    if isinstance(record, dict) and "html" in record:
        html = record["html"]

        # Name from <a> tag text
        name_match = re.search(r'<a[^>]*>([^<]+)</a>', html)
        info["name"] = name_match.group(1).strip() if name_match else ""

        # TID from href (encoded, e.g. tid=nKGmpQ==)
        tid_match = re.search(r'tid=([A-Za-z0-9+/=]+)', html)
        info["tid"] = tid_match.group(1) if tid_match else ""

        # Dates: "Mar 13, 2026 - Mar 15, 2026"
        date_match = re.search(
            r'(\w{3}\s+\d{1,2},?\s*\d{4})\s*-\s*(\w{3}\s+\d{1,2},?\s*\d{4})', html
        )
        if date_match:
            info["start_date"] = date_match.group(1).strip()
            info["end_date"] = date_match.group(2).strip()
        else:
            info["start_date"] = ""
            info["end_date"] = ""

        # State
        state_match = re.search(r'State:\s*(\w[\w\s]*?)(?:<|&|\s*$)', html)
        info["state"] = state_match.group(1).strip() if state_match else ""

        info["total_entries"] = 0  # Will be fetched from entry list or realtime API

    elif isinstance(record, dict):
        # Fallback for structured dict format
        info["name"] = _clean_html(
            record.get("name", record.get("tournament_name", ""))
        )
        info["tid"] = str(record.get("tid", record.get("id", "")))
        info["start_date"] = record.get("start_date", "")
        info["end_date"] = record.get("end_date", "")
        info["state"] = record.get("state", "")
        info["total_entries"] = _parse_int(record.get("total", 0))

    return info


def _clean_html(text):
    """Strip HTML tags from a string."""
    text = str(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip()
    return text


def _parse_int(value):
    """Safely parse an integer from various formats."""
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace(",", "")
    match = re.search(r"(\d+)", s)
    return int(match.group(1)) if match else 0


def normalize_date(date_str):
    """Parse various date formats to YYYY-MM-DD."""
    if not date_str:
        return ""
    date_str = str(date_str).strip()

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%b %d, %Y",
        "%b %d %Y",
        "%B %d, %Y",
        "%B %d %Y",
        "%d-%b-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def extract_year(record_info):
    """Extract tournament year from dates or name."""
    for field in ["start_date", "end_date"]:
        val = record_info.get(field, "")
        match = re.search(r"(20\d{2})", str(val))
        if match:
            return int(match.group(1))

    match = re.search(r"(20\d{2})", record_info.get("name", ""))
    if match:
        return int(match.group(1))

    return None


def derive_tournament_code(name):
    """
    Derive the CCA URL code from a tournament name.

    Tries known mappings first, then generates a code from initials.
    """
    name_lower = name.lower()
    # Strip leading year
    name_lower = re.sub(r"^\d{4}\s+", "", name_lower).strip()

    # Check known codes
    for pattern, code in KNOWN_CODES.items():
        if pattern in name_lower:
            return code

    # Generate from initials of significant words
    words = re.findall(r"[a-z]+", name_lower)
    skip = {"the", "of", "and", "in", "at", "for", "a", "an"}
    initials = "".join(w[0].upper() for w in words if w not in skip)
    return initials if initials else None


def fetch_entry_list_html(session, code, yy):
    """
    Fetch the HTML entry list for a tournament.

    Returns the HTML string or None if not found.
    """
    url = ENTRY_LIST_TEMPLATE.format(code=code, yy=yy)
    try:
        _rate_limit()
        resp = session.get(url, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 200 and len(resp.text) > 200:
            return resp.text
        return None
    except requests.RequestException:
        return None


def fetch_realtime_count(session, tid):
    """
    Fetch real-time entry count from CCA AJAX endpoint.

    Returns dict with total, status, registered, ref_id or None.
    """
    if not tid:
        return None
    try:
        _rate_limit()
        resp = session.get(
            REALTIME_URL,
            params={"tid": tid, "met": "0"},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        text = resp.text.strip()
        parts = text.split("|")
        if len(parts) >= 4:
            return {
                "total": _parse_int(parts[0]),
                "status": parts[1].strip(),
                "registered": _parse_int(parts[2]),
                "ref_id": parts[3].strip(),
            }
        elif len(parts) >= 1:
            return {"total": _parse_int(parts[0])}
        return None
    except requests.RequestException:
        return None


def parse_entry_list_html(html):
    """
    Parse a CCA entry list HTML page for detailed stats.

    Extracts:
      - Section breakdown (section name -> count)
      - Schedule choice distribution (3-day, 4-day, 5-day counts)
      - Player states (for geographic diversity)
      - Withdrawal count
      - USCF ratings
    """
    result = {
        "sections": {},
        "schedule_dist": {},
        "player_states": [],
        "withdrawal_count": 0,
        "ratings": [],
    }

    if not html:
        return result

    # ── Withdrawal count ──────────────────────────────────────────────
    # Pattern: "N Active Players [+M Withdrawn]" or "N Players (+M Withdrawn)"
    wd_match = re.search(
        r"(\d+)\s+Active\s+Players?\s*\[\s*\+?\s*(\d+)\s+Withdrawn\s*\]",
        html,
        re.IGNORECASE,
    )
    if not wd_match:
        wd_match = re.search(
            r"(\d+)\s+Players?\s*\(\s*\+?\s*(\d+)\s+Withdrawn\s*\)",
            html,
            re.IGNORECASE,
        )
    if wd_match:
        result["withdrawal_count"] = int(wd_match.group(2))

    # ── Section breakdown ─────────────────────────────────────────────
    # Look for section headers with counts, e.g. "Open Section (45 players)"
    # or table-based section groupings
    section_pattern = re.findall(
        r'(?:section|division)[:\s]*([^<\n(]+?)\s*[\(\[]?\s*(\d+)\s*(?:players?|entries|registered)',
        html,
        re.IGNORECASE,
    )
    if section_pattern:
        for sec_name, count in section_pattern:
            sec_name = sec_name.strip().strip(":-–")
            if sec_name:
                result["sections"][sec_name] = int(count)

    # Also try: "Section Name\n... N players" pattern in table headers
    if not result["sections"]:
        # Try to find section headers in bold/heading tags
        sec_headers = re.findall(
            r'<(?:b|strong|h[1-6])[^>]*>\s*([^<]+?(?:section|open|u\d+|under|class|reserve|premier)[^<]*?)\s*</(?:b|strong|h[1-6])>',
            html,
            re.IGNORECASE,
        )
        for header in sec_headers:
            header = _clean_html(header).strip()
            # Count rows following this header until next header
            # This is a rough heuristic — count player rows
            pattern = re.escape(header) + r'.*?(?=<(?:b|strong|h[1-6])|$)'
            block = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if block:
                player_rows = re.findall(r'\d{7,8}', block.group(0))
                if player_rows:
                    result["sections"][header] = len(player_rows)

    # ── Schedule distribution ─────────────────────────────────────────
    # Look for schedule choices like "3-Day", "4-Day", "5-Day", "2-Day"
    schedule_matches = re.findall(
        r'(\d)\s*-?\s*[Dd]ay', html
    )
    if schedule_matches:
        dist = Counter(schedule_matches)
        result["schedule_dist"] = {f"{k}-day": v for k, v in dist.items()}

    # ── Player states ─────────────────────────────────────────────────
    # CCA entry lists typically show state as 2-letter code in player rows
    # Pattern: after a USCF ID (7-8 digits), there's often a state code
    # Also try: standalone 2-letter state codes in table cells
    state_pattern = re.findall(
        r'<td[^>]*>\s*([A-Z]{2})\s*</td>', html
    )
    # Filter to valid US state codes
    valid_states = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC", "PR", "VI", "GU", "FM",
    }
    result["player_states"] = [s for s in state_pattern if s in valid_states]

    # ── USCF Ratings ──────────────────────────────────────────────────
    # Ratings are typically 3-4 digit numbers in the 100-3000 range,
    # appearing near USCF IDs (7-8 digits) in player rows
    # Look for rating patterns: a number between 100 and 2999 in table cells
    rating_candidates = re.findall(
        r'<td[^>]*>\s*(\d{3,4})\s*</td>', html
    )
    for r in rating_candidates:
        val = int(r)
        # Filter to plausible USCF rating range
        if 100 <= val <= 2999:
            result["ratings"].append(val)

    # If we got too many "ratings" relative to expected player count,
    # they might be false positives. Use a sanity check: ratings should
    # roughly equal the number of states found (both are per-player).
    n_states = len(result["player_states"])
    if n_states > 0 and len(result["ratings"]) > n_states * 3:
        # Too many — likely picking up non-rating numbers. Trim to reasonable count.
        result["ratings"] = result["ratings"][:n_states]

    return result


def process_tournament(session, record_info):
    """
    Enrich a single tournament record with entry list and realtime data.

    Returns a dict with all extracted fields.
    """
    name = record_info.get("name", "")
    tid = record_info.get("tid", "")
    year = extract_year(record_info)
    yy = str(year)[-2:] if year else ""

    start_date = normalize_date(record_info.get("start_date", ""))
    end_date = normalize_date(record_info.get("end_date", ""))
    state = record_info.get("state", "")
    total_entries = record_info.get("total_entries", 0)

    # Derive tournament code for entry list URL
    code = derive_tournament_code(name)

    # Fetch entry list HTML (if we have code and year)
    html_data = None
    if code and yy:
        html_data = fetch_entry_list_html(session, code, yy)

    # Fetch real-time count
    rt_data = fetch_realtime_count(session, tid)

    # If realtime data has a total, prefer it over the listing total
    if rt_data and rt_data.get("total", 0) > 0:
        total_entries = max(total_entries, rt_data["total"])

    # Parse HTML entry list
    parsed = parse_entry_list_html(html_data) if html_data else {
        "sections": {},
        "schedule_dist": {},
        "player_states": [],
        "withdrawal_count": 0,
        "ratings": [],
    }

    # Compute rating statistics
    ratings = parsed["ratings"]
    rating_mean = round(statistics.mean(ratings), 1) if ratings else None
    rating_median = round(statistics.median(ratings), 1) if ratings else None
    rating_std = round(statistics.stdev(ratings), 1) if len(ratings) >= 2 else None

    # Unique states
    unique_states = len(set(parsed["player_states"])) if parsed["player_states"] else None

    return {
        "tournament_name": name,
        "year": year,
        "start_date": start_date,
        "end_date": end_date,
        "state": state,
        "total_entries": total_entries,
        "sections": json.dumps(parsed["sections"]) if parsed["sections"] else "",
        "schedule_dist": json.dumps(parsed["schedule_dist"]) if parsed["schedule_dist"] else "",
        "unique_states": unique_states if unique_states else "",
        "withdrawal_count": parsed["withdrawal_count"] if parsed["withdrawal_count"] else "",
        "rating_mean": rating_mean if rating_mean else "",
        "rating_median": rating_median if rating_median else "",
        "rating_std": rating_std if rating_std else "",
    }


def save_results(results, path):
    """Write results to CSV."""
    fieldnames = [
        "tournament_name", "year", "start_date", "end_date", "state",
        "total_entries", "sections", "schedule_dist", "unique_states",
        "withdrawal_count", "rating_mean", "rating_median", "rating_std",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def print_summary(results):
    """Print summary statistics."""
    n = len(results)
    if n == 0:
        print("No tournaments processed.")
        return

    years = [r["year"] for r in results if r["year"]]
    entries = [r["total_entries"] for r in results if r["total_entries"]]
    with_sections = sum(1 for r in results if r["sections"])
    with_schedule = sum(1 for r in results if r["schedule_dist"])
    with_ratings = sum(1 for r in results if r["rating_mean"])
    with_states = sum(1 for r in results if r["unique_states"])
    with_withdrawals = sum(1 for r in results if r["withdrawal_count"])

    print(f"\n{'='*60}")
    print(f"  HISTORICAL SCRAPE SUMMARY")
    print(f"{'='*60}")
    print(f"  Total tournaments processed:  {n}")
    if years:
        print(f"  Year range:                   {min(years)} - {max(years)}")
    if entries:
        print(f"  Entry counts:                 min={min(entries)}, max={max(entries)}, "
              f"mean={statistics.mean(entries):.0f}, median={statistics.median(entries):.0f}")
    print(f"  With section breakdown:       {with_sections} ({with_sections/n*100:.1f}%)")
    print(f"  With schedule distribution:   {with_schedule} ({with_schedule/n*100:.1f}%)")
    print(f"  With rating stats:            {with_ratings} ({with_ratings/n*100:.1f}%)")
    print(f"  With geographic diversity:    {with_states} ({with_states/n*100:.1f}%)")
    print(f"  With withdrawal count:        {with_withdrawals} ({with_withdrawals/n*100:.1f}%)")

    # Per-year breakdown
    if years:
        year_counts = Counter(years)
        print(f"\n  {'Year':<8} {'Tournaments':>12} {'Avg Entries':>12}")
        print(f"  {'-'*8} {'-'*12} {'-'*12}")
        for yr in sorted(year_counts.keys()):
            yr_entries = [r["total_entries"] for r in results
                         if r["year"] == yr and r["total_entries"]]
            avg = statistics.mean(yr_entries) if yr_entries else 0
            print(f"  {yr:<8} {year_counts[yr]:>12} {avg:>12.0f}")

    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Scrape historical CCA tournament data")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit to first N tournaments (0=all, for testing)")
    parser.add_argument("--skip-html", action="store_true",
                        help="Skip HTML entry list fetches (faster, less detail)")
    parser.add_argument("--skip-realtime", action="store_true",
                        help="Skip real-time count endpoint")
    args = parser.parse_args()

    session = create_session()

    # Step 1: Fetch all completed tournaments
    raw_tournaments = fetch_completed_tournaments(session)

    if args.limit > 0:
        raw_tournaments = raw_tournaments[:args.limit]
        print(f"  Limited to first {args.limit} tournaments")

    # Step 2: Parse and enrich each tournament
    # Resume logic: load existing results to skip already-processed tournaments
    out_path = os.path.join(OUTPUT_DIR, "historical_tournaments.csv")
    results = []
    already_done = set()
    if os.path.exists(out_path):
        existing = pd.read_csv(out_path)
        for _, row in existing.iterrows():
            already_done.add((str(row.get('tournament_name', '')), int(row.get('year', 0))))
            results.append(row.to_dict())
        print(f"  Resuming: {len(already_done)} tournaments already processed")

    n_total = len(raw_tournaments)
    n_errors = 0
    n_html_found = 0
    n_skipped = 0

    print(f"\nProcessing {n_total} tournaments...", flush=True)
    for i, record in enumerate(raw_tournaments):
        try:
            record_info = parse_tournament_record(record)

            # Skip records with no name
            if not record_info.get("name"):
                continue

            # Skip already-processed tournaments (resume support)
            year = extract_year(record_info)
            if (record_info.get("name", ""), year) in already_done:
                n_skipped += 1
                continue

            # Optionally skip HTML and/or realtime fetches
            if args.skip_html and args.skip_realtime:
                # Just use the listing data
                year = extract_year(record_info)
                result = {
                    "tournament_name": record_info.get("name", ""),
                    "year": year,
                    "start_date": normalize_date(record_info.get("start_date", "")),
                    "end_date": normalize_date(record_info.get("end_date", "")),
                    "state": record_info.get("state", ""),
                    "total_entries": record_info.get("total_entries", 0),
                    "sections": "",
                    "schedule_dist": "",
                    "unique_states": "",
                    "withdrawal_count": "",
                    "rating_mean": "",
                    "rating_median": "",
                    "rating_std": "",
                }
            else:
                result = process_tournament(session, record_info)

            results.append(result)

            if result.get("sections"):
                n_html_found += 1

        except Exception as e:
            n_errors += 1
            name = ""
            try:
                name = parse_tournament_record(record).get("name", "???")
            except Exception:
                pass
            if n_errors <= 10:
                print(f"  ERROR processing tournament {i+1} ({name}): {e}")
            elif n_errors == 11:
                print("  (suppressing further error messages)")

        # Progress report + incremental save every 50
        if (i + 1) % 50 == 0 or (i + 1) == n_total:
            print(f"  [{i+1}/{n_total}] processed, "
                  f"{len(results)} valid, "
                  f"{n_html_found} with HTML data, "
                  f"{n_skipped} skipped (resume), "
                  f"{n_errors} errors", flush=True)
            save_results(results, out_path)

    # Step 3: Final save
    save_results(results, out_path)
    print(f"\nSaved {len(results)} tournaments to {out_path}")

    # Step 4: Print summary
    print_summary(results)

    if n_errors > 0:
        print(f"\n  WARNING: {n_errors} tournaments had errors during processing")


if __name__ == "__main__":
    main()
