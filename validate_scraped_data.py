"""
Data validation module for scraped CCA tournament data.

Checks output/daily_scrape.csv and output/tournament_summary.csv for
quality issues: nulls, duplicates, impossible values, malformed dates.

Usage:
    python validate_scraped_data.py
"""

import csv
import logging
import os
import re
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
DAILY_SCRAPE_CSV = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
TOURNAMENT_SUMMARY_CSV = os.path.join(OUTPUT_DIR, "tournament_summary.csv")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# daily_scrape.csv required fields (from scrape_entries.py save_csv)
DAILY_REQUIRED_FIELDS = ["date", "tournament_name", "entry_count", "url"]

# tournament_summary.csv required fields
SUMMARY_REQUIRED_FIELDS = ["tid", "tournament_name", "final_count", "tournament_year"]


class ValidationReport:
    """Stores validation results with errors (blocking) and warnings (non-blocking)."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    @property
    def passed(self):
        return len(self.errors) == 0

    def add_error(self, msg):
        self.errors.append(msg)
        logger.error(msg)

    def add_warning(self, msg):
        self.warnings.append(msg)
        logger.warning(msg)

    def merge(self, other):
        """Merge another ValidationReport into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def summary(self):
        """Print a formatted validation report."""
        status = "PASS" if self.passed else "FAIL"
        lines = [
            "",
            "=" * 60,
            f"  VALIDATION REPORT — {status}",
            "=" * 60,
        ]

        if self.errors:
            lines.append(f"\n  ERRORS ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"    [ERROR] {e}")

        if self.warnings:
            lines.append(f"\n  WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"    [WARN]  {w}")

        if not self.errors and not self.warnings:
            lines.append("  No issues found.")

        lines.append("=" * 60)
        lines.append("")
        return "\n".join(lines)


def _read_csv(csv_path):
    """Read a CSV file and return (rows, fieldnames). Returns ([], []) if file missing."""
    if not os.path.exists(csv_path):
        return [], []
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return rows, fieldnames


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

    rows, fieldnames = _read_csv(csv_path)

    if not rows:
        report.add_error(f"File is empty: {csv_path}")
        return report

    # Check required columns exist in header
    for field in DAILY_REQUIRED_FIELDS:
        if field not in fieldnames:
            report.add_error(f"Missing required column: {field}")

    if report.errors:
        return report  # can't check rows without required columns

    # Row-level checks
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

        # Date format check
        date_val = row.get("date", "").strip()
        if date_val and not DATE_RE.match(date_val):
            report.add_error(f"Row {i}: malformed date '{date_val}' (expected YYYY-MM-DD)")
        elif date_val:
            try:
                datetime.strptime(date_val, "%Y-%m-%d")
            except ValueError:
                report.add_error(f"Row {i}: invalid date '{date_val}'")

        # Entry count range check
        count_val = row.get("entry_count", "").strip()
        if count_val and count_val.lower() != "nan":
            try:
                count = int(count_val)
                if count < 0:
                    report.add_error(f"Row {i}: negative entry_count ({count}) for {row.get('tournament_name')}")
                elif count > 10000:
                    report.add_error(f"Row {i}: entry_count ({count}) exceeds 10000 for {row.get('tournament_name')}")
            except ValueError:
                report.add_error(f"Row {i}: non-numeric entry_count '{count_val}'")

    if null_count:
        report.add_warning(f"Total null/empty field occurrences: {null_count}")
    if dup_count:
        report.add_error(f"Total duplicate entries: {dup_count}")

    logger.info("daily_scrape: %d rows checked, %d errors, %d warnings",
                len(rows), len(report.errors), len(report.warnings))
    return report


def validate_tournament_summary(csv_path=None):
    """
    Validate output/tournament_summary.csv for quality issues.

    Checks:
      - File exists and is non-empty
      - Null final_count values
      - Duplicate tournament IDs (tid)
      - final_count < 0 or > 10000
      - tournament_year outside reasonable range (2000-2030)
    """
    if csv_path is None:
        csv_path = TOURNAMENT_SUMMARY_CSV

    report = ValidationReport()
    logger.info("Validating %s", csv_path)

    if not os.path.exists(csv_path):
        report.add_warning(f"File not found (optional): {csv_path}")
        return report

    rows, fieldnames = _read_csv(csv_path)

    if not rows:
        report.add_warning(f"File is empty: {csv_path}")
        return report

    # Check key columns exist
    for field in SUMMARY_REQUIRED_FIELDS:
        if field not in fieldnames:
            report.add_error(f"Missing required column: {field}")

    if report.errors:
        return report

    tid_set = set()
    null_final = 0

    for i, row in enumerate(rows, start=2):
        # Null final_count
        fc_val = row.get("final_count", "").strip()
        if fc_val == "" or fc_val.lower() == "nan" or fc_val is None:
            null_final += 1
            report.add_warning(f"Row {i}: null/empty final_count for tid={row.get('tid')}")
        else:
            try:
                fc = int(float(fc_val))
                if fc < 0:
                    report.add_error(f"Row {i}: negative final_count ({fc}) for tid={row.get('tid')}")
                elif fc > 10000:
                    report.add_error(f"Row {i}: final_count ({fc}) exceeds 10000 for tid={row.get('tid')}")
            except ValueError:
                report.add_error(f"Row {i}: non-numeric final_count '{fc_val}'")

        # Duplicate tid
        tid = row.get("tid", "").strip()
        if tid:
            if tid in tid_set:
                report.add_error(f"Row {i}: duplicate tid={tid}")
            tid_set.add(tid)

        # tournament_year range
        year_val = row.get("tournament_year", "").strip()
        if year_val and year_val.lower() != "nan" and year_val != "":
            try:
                year = int(float(year_val))
                if year < 2000 or year > 2030:
                    report.add_warning(f"Row {i}: tournament_year ({year}) outside 2000-2030 for tid={row.get('tid')}")
            except ValueError:
                report.add_warning(f"Row {i}: non-numeric tournament_year '{year_val}'")

    if null_final:
        report.add_warning(f"Total rows with null final_count: {null_final}")

    logger.info("tournament_summary: %d rows checked, %d errors, %d warnings",
                len(rows), len(report.errors), len(report.warnings))
    return report


def validate_metadata_freshness(csv_path=None, year=None):
    """Surface upcoming events with degraded model features (missing early-bird
    deadline). The deadline drives days_to_early_bird in feature_engineering;
    when missing, the model uses neutral values — silent degradation.
    AUDIT.md A3.
    """
    import os
    import pandas as pd
    report = ValidationReport()
    if csv_path is None:
        OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        csv_path = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
    if not os.path.exists(csv_path):
        report.add_warning(f"{csv_path} not found")
        return report
    m = pd.read_csv(csv_path)
    m['start_date'] = pd.to_datetime(m['start_date'], errors='coerce')
    m['early_bird_deadline'] = pd.to_datetime(m['early_bird_deadline'], errors='coerce')
    today = pd.Timestamp.now().normalize()
    if year is None:
        year = today.year
    upcoming = m[(m['year'] == year) & (m['start_date'] > today)]
    no_eb = upcoming[upcoming['early_bird_deadline'].isna()]
    if len(no_eb) > 0:
        report.add_warning(
            f"{len(no_eb)} upcoming {year} event(s) missing early_bird_deadline "
            f"in tournament_metadata.csv — model will use neutral feature values. "
            f"Run update_metadata.py to populate."
        )
    return report


def validate_all():
    """Run all validators and return a combined ValidationReport."""
    combined = ValidationReport()

    daily_report = validate_daily_scrape()
    combined.merge(daily_report)

    summary_report = validate_tournament_summary()
    combined.merge(summary_report)

    metadata_report = validate_metadata_freshness()
    combined.merge(metadata_report)

    return combined


def main():
    report = validate_all()
    print(report.summary())

    if not report.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
