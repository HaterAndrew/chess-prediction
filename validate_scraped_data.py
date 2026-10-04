"""
Data validation module for scraped CCA tournament data.

Checks output/daily_scrape.csv, output/tournament_summary.csv and
output/tournament_metadata.csv for quality issues: nulls, duplicates,
impossible values, malformed dates, upcoming events with no flyer.

The checks live in validation/; this module stays the CLI and the import
surface auto_update, backfill_missing_data and the tests use.

Usage:
    python validate_scraped_data.py
"""

import logging
import sys

from validation.metadata import validate_metadata_freshness
from validation.report import ValidationReport
from validation.scrape import (  # noqa: F401
    DAILY_REQUIRED_FIELDS,
    DAILY_SCRAPE_CSV,
    DATE_RE,
    validate_daily_scrape,
)
from validation.summary import (  # noqa: F401
    SUMMARY_REQUIRED_FIELDS,
    TOURNAMENT_SUMMARY_CSV,
    validate_tournament_summary,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

__all__ = [
    "ValidationReport",
    "validate_all",
    "validate_daily_scrape",
    "validate_metadata_freshness",
    "validate_tournament_summary",
]


def validate_all():
    """Run all validators and return a combined ValidationReport."""
    combined = ValidationReport()
    combined.merge(validate_daily_scrape())
    combined.merge(validate_tournament_summary())
    combined.merge(validate_metadata_freshness())
    return combined


def main():
    report = validate_all()
    print(report.summary())

    if not report.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
