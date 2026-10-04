"""Checks on output/tournament_summary.csv."""
import logging
import os

from shared.paths import SUMMARY_CSV as TOURNAMENT_SUMMARY_CSV
from validation.report import ValidationReport, read_csv

logger = logging.getLogger(__name__)

# tournament_summary.csv required fields
SUMMARY_REQUIRED_FIELDS = ["tid", "tournament_name", "final_count", "tournament_year"]


def _check_final_count(report, i, row):
    """Returns True when final_count is null."""
    fc_val = (row.get("final_count") or "").strip()
    if fc_val == "" or fc_val.lower() == "nan":
        report.add_warning(f"Row {i}: null/empty final_count for tid={row.get('tid')}")
        return True
    try:
        fc = int(float(fc_val))
    except ValueError:
        report.add_error(f"Row {i}: non-numeric final_count '{fc_val}'")
        return False
    if fc < 0:
        report.add_error(f"Row {i}: negative final_count ({fc}) for tid={row.get('tid')}")
    elif fc > 10000:
        report.add_error(f"Row {i}: final_count ({fc}) exceeds 10000 for tid={row.get('tid')}")
    return False


def _check_year(report, i, row):
    year_val = (row.get("tournament_year") or "").strip()
    if not year_val or year_val.lower() == "nan":
        return
    try:
        year = int(float(year_val))
    except ValueError:
        report.add_warning(f"Row {i}: non-numeric tournament_year '{year_val}'")
        return
    if year < 2000 or year > 2030:
        report.add_warning(f"Row {i}: tournament_year ({year}) outside 2000-2030 for tid={row.get('tid')}")


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

    rows, fieldnames = read_csv(csv_path)

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
        if _check_final_count(report, i, row):
            null_final += 1

        # Duplicate tid
        tid = (row.get("tid") or "").strip()
        if tid:
            if tid in tid_set:
                report.add_error(f"Row {i}: duplicate tid={tid}")
            tid_set.add(tid)

        _check_year(report, i, row)

    if null_final:
        report.add_warning(f"Total rows with null final_count: {null_final}")

    logger.info("tournament_summary: %d rows checked, %d errors, %d warnings",
                len(rows), len(report.errors), len(report.warnings))
    return report
