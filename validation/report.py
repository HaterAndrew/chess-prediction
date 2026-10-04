"""ValidationReport and the CSV reader the validators share."""
import csv
import logging
import os

logger = logging.getLogger(__name__)


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


def read_csv(csv_path):
    """Read a CSV file and return (rows, fieldnames). Returns ([], []) if file missing."""
    if not os.path.exists(csv_path):
        return [], []
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return rows, fieldnames
