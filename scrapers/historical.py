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
  python scrape_historical.py --full --out <path outside output/>
      # scrape everything again and print what changed
"""

import os
import argparse

import pandas as pd

from scraper_utils import polite_session, rate_limit as _rate_limit, DEFAULT_TIMEOUT
from scrapers.historical_enrich import (  # noqa: F401
    REALTIME_URL, fetch_realtime_count, listing_only, process_tournament)
from scrapers.historical_entry_list import (  # noqa: F401
    ENTRY_LIST_TEMPLATE, fetch_entry_list_html, parse_entry_list_html)
from scrapers.historical_output import print_refresh_diff, print_summary, save_results
from scrapers.historical_record import (  # noqa: F401
    KNOWN_CODES, _parse_int, derive_tournament_code, extract_year, normalize_date,
    parse_tournament_record)

# __file__-derived paths do not survive relocation into a package (P7).
from shared.paths import OUTPUT_DIR, PROJECT_DIR  # noqa: F401
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "https://www.chessaction.com"
COMPLETED_URL = f"{BASE_URL}/ajaxFrontGetCompletedTourListForAllNew.php"


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


HISTORICAL_CSV = os.path.join(OUTPUT_DIR, "historical_tournaments.csv")


def _resume(path):
    """(rows on file, their (name, year) keys); a run skips those editions."""
    if not os.path.exists(path):
        return [], set()
    rows = [row.to_dict() for _, row in pd.read_csv(path).iterrows()]
    done = {(str(r.get('tournament_name', '')), int(r.get('year', 0))) for r in rows}
    print(f"  Resuming: {len(done)} tournaments already processed")
    return rows, done


def _out_path(args, parser):
    """output/historical_tournaments.csv, or for --full the --out path, which
    must lie outside output/: verify_checksums hashes every CSV there, and a
    full refresh is reviewed before it replaces the file on record."""
    if not args.full:
        if args.out:
            parser.error("--out is only for --full")
        return HISTORICAL_CSV
    if not args.out:
        parser.error("--full needs --out <path outside output/>")
    out = os.path.normcase(os.path.abspath(args.out))
    if out.startswith(os.path.normcase(os.path.abspath(OUTPUT_DIR)) + os.sep):
        parser.error(f"--out {args.out} is inside output/")
    return args.out


def _report_error(n_errors, i, record, exc):
    if n_errors > 11:
        return
    if n_errors == 11:
        print("  (suppressing further error messages)")
        return
    try:
        name = parse_tournament_record(record).get("name", "???")
    except Exception:
        name = ""
    print(f"  ERROR processing tournament {i+1} ({name}): {exc}")


def main():
    parser = argparse.ArgumentParser(description="Scrape historical CCA tournament data")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit to first N tournaments (0=all, for testing)")
    parser.add_argument("--skip-html", action="store_true",
                        help="Skip HTML entry list fetches (faster, less detail)")
    parser.add_argument("--skip-realtime", action="store_true",
                        help="Skip real-time count endpoint")
    parser.add_argument("--full", action="store_true",
                        help="Scrape every tournament again instead of resuming, write to --out, "
                             "and print what changed against output/historical_tournaments.csv")
    parser.add_argument("--out", help="Output path for --full, outside output/")
    args = parser.parse_args()
    out_path = _out_path(args, parser)

    session = create_session()

    # Step 1: Fetch all completed tournaments
    raw_tournaments = fetch_completed_tournaments(session)

    if args.limit > 0:
        raw_tournaments = raw_tournaments[:args.limit]
        print(f"  Limited to first {args.limit} tournaments")

    # Step 2: Parse and enrich each tournament, skipping the editions on file
    # unless this is a full refresh
    results, already_done = ([], set()) if args.full else _resume(out_path)

    n_total = len(raw_tournaments)
    n_errors = 0
    n_html_found = 0
    n_skipped = 0

    print(f"\nProcessing {n_total} tournaments...", flush=True)
    for i, record in enumerate(raw_tournaments):
        try:
            record_info = parse_tournament_record(record)
            key = (record_info.get("name", ""), extract_year(record_info))
            if not key[0]:
                pass
            elif key in already_done:
                n_skipped += 1
            else:
                listing = args.skip_html and args.skip_realtime
                result = listing_only(record_info) if listing else process_tournament(session, record_info)
                results.append(result)
                n_html_found += bool(result.get("sections"))
        except Exception as e:
            n_errors += 1
            _report_error(n_errors, i, record, e)

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
    if args.full and os.path.exists(HISTORICAL_CSV):
        print_refresh_diff(HISTORICAL_CSV, out_path)

    if n_errors > 0:
        print(f"\n  WARNING: {n_errors} tournaments had errors during processing")


if __name__ == "__main__":
    main()
