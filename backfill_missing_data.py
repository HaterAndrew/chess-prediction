"""
Backfill script for recovering from multi-day scrape failures.

Identifies date gaps in output/daily_scrape.csv and runs the scraper to fill
them. CCA shows live data, so backfilled rows reflect counts at backfill time.

Usage:
    python backfill_missing_data.py scan                    # show gaps
    python backfill_missing_data.py fill                    # fill all gaps
    python backfill_missing_data.py fill --date 2026-04-10  # fill one date
    python backfill_missing_data.py fill --dry-run          # preview only
"""

import argparse
import csv
import logging
import os
import sys
from datetime import datetime, timedelta

from scraper_utils import rate_limit
from validate_scraped_data import validate_daily_scrape

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
CSV_PATH = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
FIELDNAMES = ["date", "tournament_name", "entry_count", "url"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def find_gaps(csv_path=CSV_PATH):
    """Return sorted list of YYYY-MM-DD strings missing between earliest and latest dates."""
    if not os.path.exists(csv_path):
        logger.error("CSV not found: %s", csv_path)
        return []
    with open(csv_path, "r", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        logger.warning("CSV is empty.")
        return []

    dates_present = {r["date"].strip() for r in rows if r.get("date", "").strip()}
    if len(dates_present) < 2:
        logger.info("Fewer than 2 distinct dates — no gaps possible.")
        return []

    sorted_dates = sorted(dates_present)
    start = datetime.strptime(sorted_dates[0], "%Y-%m-%d").date()
    end = datetime.strptime(sorted_dates[-1], "%Y-%m-%d").date()
    all_dates = set()
    cur = start
    while cur <= end:
        all_dates.add(cur.isoformat())
        cur += timedelta(days=1)

    missing = sorted(all_dates - dates_present)
    logger.info("Range %s..%s (%d days). Present: %d. Missing: %d.",
                sorted_dates[0], sorted_dates[-1],
                (end - start).days + 1, len(dates_present), len(missing))
    return missing


def backfill_date(date_str):
    """Scrape CCA and return rows tagged with date_str."""
    from scrape_entries import scrape_index, consolidate_world_open

    rate_limit(min_delay=1.0, max_delay=2.0)
    logger.info("Scraping CCA for backfill date %s ...", date_str)
    tournaments = scrape_index()
    if not tournaments:
        logger.warning("No tournaments returned for %s", date_str)
        return []
    consolidated = consolidate_world_open(tournaments)
    rows = [{"date": date_str, "tournament_name": t["name"],
             "entry_count": str(t["entry_count"]), "url": t["url"]}
            for t in consolidated]
    logger.info("Scraped %d tournaments for %s", len(rows), date_str)
    return rows


def merge_backfill(existing_csv, new_rows, dry_run=False):
    """Merge new_rows into CSV. Preserves existing; adds only missing (date, name) pairs.
    Returns (merged_rows, ValidationReport)."""
    if not os.path.exists(existing_csv):
        logger.error("CSV not found: %s", existing_csv)
        return [], None
    with open(existing_csv, "r", newline="") as f:
        existing = list(csv.DictReader(f))

    index = {(r["date"], r["tournament_name"]): r for r in existing}
    added = 0
    for row in new_rows:
        key = (row["date"], row["tournament_name"])
        if key not in index:
            index[key] = row
            added += 1

    merged = sorted(index.values(), key=lambda r: (r["date"], r["tournament_name"]))
    logger.info("Merge: %d existing + %d new = %d total", len(existing), added, len(merged))

    if not dry_run:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(existing_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(merged)
        logger.info("Wrote %d rows to %s", len(merged), existing_csv)

    report = validate_daily_scrape(existing_csv)
    return merged, report


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_scan(_args):
    """Show gaps without fixing anything."""
    gaps = find_gaps(CSV_PATH)
    if not gaps:
        print("No gaps found.")
        return
    print(f"\n{len(gaps)} missing date(s):")
    for d in gaps:
        print(f"  {d}")
    print()


def cmd_fill(args):
    """Run backfill for gaps or a specific date."""
    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            logger.error("Invalid date format: %s (expected YYYY-MM-DD)", args.date)
            sys.exit(1)
        targets = [args.date]
        logger.info("Backfill target: %s", args.date)
    else:
        targets = find_gaps(CSV_PATH)
        if not targets:
            print("No gaps found — nothing to backfill.")
            return

    if args.dry_run:
        print(f"\n[DRY RUN] Would backfill {len(targets)} date(s):")
        for d in targets:
            print(f"  {d}")
        print("\nNo changes written.")
        return

    all_new_rows = []
    for i, date_str in enumerate(targets, 1):
        logger.info("Backfilling %d/%d: %s", i, len(targets), date_str)
        rows = backfill_date(date_str)
        all_new_rows.extend(rows)
        if i < len(targets):
            rate_limit(min_delay=2.0, max_delay=4.0)

    if not all_new_rows:
        logger.warning("No rows scraped — nothing to merge.")
        return

    merged, report = merge_backfill(CSV_PATH, all_new_rows)
    print(report.summary())
    if not report.passed:
        logger.error("Validation failed after merge — review errors above.")
        sys.exit(1)
    logger.info("Backfill complete. %d date(s) filled.", len(targets))


def main():
    parser = argparse.ArgumentParser(description="Backfill missing dates in daily_scrape.csv")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="Show date gaps")
    fill_p = sub.add_parser("fill", help="Run backfill for missing dates")
    fill_p.add_argument("--date", help="Backfill a specific date (YYYY-MM-DD)")
    fill_p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    {"scan": cmd_scan, "fill": cmd_fill}[args.command](args)


if __name__ == "__main__":
    main()
