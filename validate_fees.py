"""
validate_fees.py — Live audit of early-bird / fee data vs the source flyer.

Loads tournament_metadata.csv, fetches the matching chesstour.com flyer
for each upcoming (year=2026+) tournament that carries any fee signal,
runs the parse_flyer() guardrails against the live HTML, and writes a
markdown report to audit/eb-verification/<date>.md with three buckets:

  OK          — metadata matches what the live flyer says
  DRIFT       — metadata disagrees with the flyer (numbers or deadline off)
  PHANTOM_EB  — metadata carries early_bird_* fields but the flyer
                doesn't support a real early bird (no price hike, no
                multi-tier structure, or deadline too close to event)

Exit status:
  0 if no PHANTOM_EB and no DRIFT
  1 if any DRIFT or PHANTOM_EB row exists (suitable for CI use)

Usage:
  python3 validate_fees.py                  # all 2026+ rows with fees
  python3 validate_fees.py --year 2026      # one year
  python3 validate_fees.py --family "Cleveland Open"
"""

import argparse
import csv
import logging
import os
import sys
from datetime import datetime, date

import requests

from scrape_fees import (
    parse_flyer,
    EARLY_BIRD_MIN_GAP_DAYS,
)
from scraper_utils import polite_session, respectful_get, DEFAULT_TIMEOUT

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
AUDIT_DIR = os.path.join(PROJECT_DIR, "audit", "eb-verification")
META_PATH = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")

# Known short-code overrides; everything else falls back to brute-force
# (the production scrape_fees.py also tries chessevents.com discovery — we
# keep this file simple and rely on a per-family lookup table that grows
# as new tournaments get verified once).
FAMILY_TO_CODE = {
    "Chicago Open": "chio",
    "Cleveland Open": "clev",
    "Pittsburgh Open": "pit",
    "Pacific Coast Open": "pco",
    "National Chess Congress": "ncc",
    "Liberty Bell Open": "lbo",
    "Golden State Open": "gso",
    "Mid-America Open": "mao",
    "Chicago Class": "chcc",
    "World Open": "wo",
    "World Open top 6 sections": "wo",
    "North American Open": "nao",
    "Boston Chess Congress": "bcc",
    "Eastern Chess Congress": "ecc",
    "Continental Class": "ccc",
    "Hartford Open": "ho",
    "New York State Open": "nyso",
    "DC International": "dci",
    "DC Open": "dco",
    "World Open lower sections": "wolower",
    "World Open Under 13 Championship": "wu",
}

_session = polite_session()


def candidate_urls(family, year):
    """URLs to try in priority order for a given (family, year)."""
    code = FAMILY_TO_CODE.get(family)
    yy = str(year)[2:]
    out = []
    if code:
        out.append(f"https://www.chesstour.com/{code}{yy}.htm")
        out.append(f"https://www.chesstour.com/{code}{year}.htm")
    return out


def fetch_html(url):
    try:
        resp = respectful_get(_session, url, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as exc:
        return None, str(exc)
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"
    resp.encoding = resp.apparent_encoding or "latin-1"
    return resp.text, None


def compare(meta_row, flyer):
    """Return (verdict, notes) — verdict ∈ {OK, DRIFT, PHANTOM_EB, NOT_FOUND}."""
    if flyer is None:
        return "NOT_FOUND", ["flyer not located on chesstour.com (probe URLs missed)"]

    notes = []
    meta_eb_dl = (meta_row.get("early_bird_deadline") or "").strip()
    meta_eb_fee = (meta_row.get("early_bird_fee") or "").strip()
    meta_reg_fee = (meta_row.get("regular_fee") or "").strip()
    meta_onsite = (meta_row.get("onsite_fee") or "").strip()

    flyer_eb_dl = str(flyer.get("early_bird_deadline") or "").strip()
    flyer_eb_fee = str(flyer.get("early_bird_fee") or "").strip()
    flyer_reg_fee = str(flyer.get("regular_fee") or "").strip()
    flyer_onsite = str(flyer.get("onsite_fee") or "").strip()
    flyer_demote = flyer.get("eb_demoted_reason") or ""

    def _num_eq(a, b):
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return a == b

    # PHANTOM_EB: metadata claims EB but flyer guardrails reject it
    if meta_eb_dl and meta_eb_fee and flyer_demote:
        notes.append(f"metadata has eb_dl={meta_eb_dl}, eb_fee=${meta_eb_fee}, "
                     f"but flyer guardrails rejected: {flyer_demote}")
        return "PHANTOM_EB", notes
    if meta_eb_dl and meta_eb_fee and not flyer_eb_dl:
        notes.append("metadata has EB fields but flyer found no qualifying early bird")
        return "PHANTOM_EB", notes

    # DRIFT: numbers disagree
    drift = []
    if meta_eb_dl and flyer_eb_dl and meta_eb_dl != flyer_eb_dl:
        drift.append(f"eb_deadline: meta={meta_eb_dl} flyer={flyer_eb_dl}")
    if meta_eb_fee and flyer_eb_fee and not _num_eq(meta_eb_fee, flyer_eb_fee):
        drift.append(f"eb_fee: meta=${meta_eb_fee} flyer=${flyer_eb_fee}")
    if meta_reg_fee and flyer_reg_fee and not _num_eq(meta_reg_fee, flyer_reg_fee):
        drift.append(f"regular_fee: meta=${meta_reg_fee} flyer=${flyer_reg_fee}")
    if meta_onsite and flyer_onsite and not _num_eq(meta_onsite, flyer_onsite):
        drift.append(f"onsite_fee: meta=${meta_onsite} flyer=${flyer_onsite}")

    if drift:
        return "DRIFT", drift
    return "OK", notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--family", help="Restrict to one family name (exact match)")
    ap.add_argument("--out", default=None, help="Markdown report path")
    args = ap.parse_args()

    os.makedirs(AUDIT_DIR, exist_ok=True)
    today_iso = date.today().isoformat()
    out_path = args.out or os.path.join(AUDIT_DIR, f"{today_iso}.md")

    rows = list(csv.DictReader(open(META_PATH)))
    targets = []
    for r in rows:
        if int(r.get("year", "0") or 0) != args.year:
            continue
        if args.family and r["family"] != args.family:
            continue
        # Only audit rows that carry any fee signal at all
        if not any(r.get(k) for k in ("early_bird_deadline", "early_bird_fee", "regular_fee", "onsite_fee")):
            continue
        targets.append(r)

    log.info("Auditing %d row(s) for year=%s", len(targets), args.year)

    results = []  # list of (family, year, url, verdict, notes, flyer)
    for r in targets:
        fam, yr = r["family"], int(r["year"])
        urls = candidate_urls(fam, yr)
        flyer = None
        used_url = None
        for u in urls:
            log.info("  fetching %s ...", u)
            html, err = fetch_html(u)
            if html is None:
                log.info("    miss (%s)", err)
                continue
            flyer = parse_flyer(html, u)
            used_url = u
            if flyer:
                break
        verdict, notes = compare(r, flyer)
        results.append((fam, yr, used_url, verdict, notes, flyer))
        log.info("  %-12s %s %s", verdict, fam, used_url or "(no live URL found)")

    # ── Write report ──────────────────────────────────────────────────
    counts = {"OK": 0, "DRIFT": 0, "PHANTOM_EB": 0, "NOT_FOUND": 0}
    for _, _, _, v, _, _ in results:
        counts[v] = counts.get(v, 0) + 1

    lines = []
    lines.append(f"# Fee data audit — year {args.year}")
    lines.append(f"_Generated {datetime.now().isoformat(timespec='seconds')}_")
    lines.append("")
    lines.append("**Source:** live `chesstour.com` flyer pages parsed by `scrape_fees.parse_flyer`.")
    lines.append(f"**Rule:** early-bird requires (a) ≥2 tiers with eb_fee < next_fee AND (b) deadline ≥ T-{EARLY_BIRD_MIN_GAP_DAYS} days before event_start.")
    lines.append("")
    lines.append("| Verdict | Count |")
    lines.append("|---|---|")
    for v in ("OK", "DRIFT", "PHANTOM_EB", "NOT_FOUND"):
        lines.append(f"| {v} | {counts.get(v, 0)} |")
    lines.append("")
    for bucket in ("PHANTOM_EB", "DRIFT", "NOT_FOUND", "OK"):
        bucket_rows = [r for r in results if r[3] == bucket]
        if not bucket_rows:
            continue
        lines.append(f"## {bucket}")
        for fam, yr, url, v, notes, flyer in bucket_rows:
            lines.append(f"### {fam} {yr}")
            lines.append(f"- URL: {url or '_(none)_'}")
            for n in notes:
                lines.append(f"- {n}")
            if flyer:
                lines.append(f"- flyer: event_start={flyer.get('event_start')}, "
                             f"eb={flyer.get('early_bird_fee')}@{flyer.get('early_bird_deadline')}, "
                             f"reg={flyer.get('regular_fee')}, onsite={flyer.get('onsite_fee')}")
            lines.append("")

    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    log.info("Wrote %s", out_path)

    bad = counts.get("DRIFT", 0) + counts.get("PHANTOM_EB", 0)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
