"""Checks on output/daily_scrape.csv."""
import logging
import os
import re
from datetime import datetime

from shared.paths import SCRAPE_CSV as DAILY_SCRAPE_CSV
from validation.report import ValidationReport, read_csv

logger = logging.getLogger(__name__)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# daily_scrape.csv required fields (from scrape_entries.py save_csv)
DAILY_REQUIRED_FIELDS = ["date", "tournament_name", "entry_count", "url"]


def _check_date(report, i, date_val):
    if not date_val:
        return
    if not DATE_RE.match(date_val):
        report.add_error(f"Row {i}: malformed date '{date_val}' (expected YYYY-MM-DD)")
        return
    try:
        datetime.strptime(date_val, "%Y-%m-%d")
    except ValueError:
        report.add_error(f"Row {i}: invalid date '{date_val}'")


def _check_count(report, i, row):
    count_val = (row.get("entry_count") or "").strip()
    if not count_val or count_val.lower() == "nan":
        return
    try:
        count = int(count_val)
    except ValueError:
        report.add_error(f"Row {i}: non-numeric entry_count '{count_val}'")
        return
    if count < 0:
        report.add_error(f"Row {i}: negative entry_count ({count}) for {row.get('tournament_name')}")
    elif count > 10000:
        report.add_error(f"Row {i}: entry_count ({count}) exceeds 10000 for {row.get('tournament_name')}")


def validate_daily_scrape(csv_path=None):
    """
    Validate output/daily_scrape.csv for quality issues.

    Checks:
      - File exists and is non-empty
      - Required fields present
      - Null/NaN entry counts
      - Duplicate tournament entries (same tournament_name + date)
      - Impossible values (negative counts, counts > 10000)
      - Malformed dates (not YYYY-MM-DD)
      - Missing required fields in individual rows
    """
    if csv_path is None:
        csv_path = DAILY_SCRAPE_CSV

    report = ValidationReport()
    logger.info("Validating %s", csv_path)

    if not os.path.exists(csv_path):
        report.add_error(f"File not found: {csv_path}")
        return report

    rows, fieldnames = read_csv(csv_path)

    if not rows:
        report.add_error(f"File is empty: {csv_path}")
        return report

    # Check required columns exist in header
    for field in DAILY_REQUIRED_FIELDS:
        if field not in fieldnames:
            report.add_error(f"Missing required column: {field}")

    if report.errors:
        return report  # can't check rows without required columns

    null_count = 0
    dup_set = set()
    dup_count = 0

    for i, row in enumerate(rows, start=2):  # row 2 = first data row (1-indexed + header)
        # Missing / null required fields
        for field in DAILY_REQUIRED_FIELDS:
            val = row.get(field, "")
            if val is None or val.strip() == "" or val.strip().lower() == "nan":
                null_count += 1
                report.add_warning(f"Row {i}: null/empty '{field}'")

        # Duplicate check (tournament_name + date)
        key = (row.get("date", ""), row.get("tournament_name", ""))
        if key in dup_set:
            dup_count += 1
            report.add_error(f"Row {i}: duplicate entry {key[1]} on {key[0]}")
        dup_set.add(key)

        _check_date(report, i, (row.get("date") or "").strip())
        _check_count(report, i, row)

    if null_count:
        report.add_warning(f"Total null/empty field occurrences: {null_count}")
    if dup_count:
        report.add_error(f"Total duplicate entries: {dup_count}")

    logger.info("daily_scrape: %d rows checked, %d errors, %d warnings",
                len(rows), len(report.errors), len(report.warnings))
    return report
