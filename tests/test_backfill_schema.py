"""Guards for the two P0s found in the 2026-09-07 review.

1. backfill_missing_data.py carried its own copy of the daily_scrape.csv
   schema. It went stale when active_count/withdrawal_count were added, and
   because merge_backfill() truncated the destination before writing, the
   DictWriter extrasaction='raise' fired AFTER the file was already emptied.
   One `backfill_missing_data.py fill` wiped the file the whole nightly
   pipeline reads down to a bare header.

2. .gitignore covered output/*.csv but nothing at repo root, so the hotel-audit
   export and workbook — names, cities, ZIPs and payer links for ~1.9K people
   including parents of minors — were one `git add -A` from a public repo.

Both tests assert the property, not the current implementation: the schema is
pinned to the scraper that owns it, and the ignore rules are checked through
git itself rather than by string-matching .gitignore.
"""
import csv
import os
import pathlib
import subprocess
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import backfill_missing_data as backfill  # noqa: E402
from scrapers.entries import CSV_FIELDS  # noqa: E402

REPO = pathlib.Path(PROJECT_DIR)


def _write_scrape_csv(path, rows, fields=CSV_FIELDS):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _row(date, name, entries=100):
    return {"date": date, "tournament_name": name,
            "entry_count": str(entries), "active_count": str(entries),
            "withdrawal_count": "0", "url": f"https://example.invalid/{name}"}


def test_backfill_schema_is_not_a_local_copy():
    """The writer's field list must be the scraper's, not a duplicate.

    This is the actual defect: a second declaration that nothing kept in sync.
    """
    assert backfill.FIELDNAMES is CSV_FIELDS


def test_merge_preserves_every_column_and_row(tmp_path):
    """A no-op merge round-trips the real six-column schema unchanged."""
    csv_path = tmp_path / "daily_scrape.csv"
    rows = [_row("2026-09-01", "Southern Open"),
            _row("2026-09-02", "Southern Open", 120)]
    _write_scrape_csv(csv_path, rows)

    merged, _ = backfill.merge_backfill(str(csv_path), [], dry_run=False)

    after = list(csv.DictReader(open(csv_path)))
    assert list(after[0].keys()) == CSV_FIELDS
    assert len(after) == len(rows)
    assert after == rows
    assert len(merged) == len(rows)


def test_merge_adds_new_rows_without_dropping_columns(tmp_path):
    csv_path = tmp_path / "daily_scrape.csv"
    _write_scrape_csv(csv_path, [_row("2026-09-01", "Southern Open")])

    merged, _ = backfill.merge_backfill(
        str(csv_path), [_row("2026-09-02", "Continental Open", 88)],
        dry_run=False)

    after = list(csv.DictReader(open(csv_path)))
    assert len(after) == 2
    assert list(after[0].keys()) == CSV_FIELDS
    added = [r for r in after if r["tournament_name"] == "Continental Open"][0]
    assert added["active_count"] == "88"
    assert added["withdrawal_count"] == "0"
    assert len(merged) == 2


def test_legacy_four_column_rows_are_upgraded_not_rejected(tmp_path):
    """Oldest corpus rows predate active_count/withdrawal_count.

    They must be filled with the same defaults the scraper uses, not written
    as blanks (which downstream readers coerce to zero entries).
    """
    csv_path = tmp_path / "daily_scrape.csv"
    legacy = ["date", "tournament_name", "entry_count", "url"]
    _write_scrape_csv(csv_path, [{"date": "2026-08-01",
                                  "tournament_name": "Bradley Open",
                                  "entry_count": "75",
                                  "url": "https://example.invalid/b"}],
                      fields=legacy)

    backfill.merge_backfill(str(csv_path), [], dry_run=False)

    after = list(csv.DictReader(open(csv_path)))
    assert list(after[0].keys()) == CSV_FIELDS
    assert after[0]["active_count"] == "75"
    assert after[0]["withdrawal_count"] == "0"


def test_failed_write_leaves_the_original_intact(tmp_path, monkeypatch):
    """The regression that mattered: never truncate before the write succeeds.

    Force the serialization to blow up mid-write and assert the destination
    still holds its rows.
    """
    csv_path = tmp_path / "daily_scrape.csv"
    rows = [_row("2026-09-01", "Southern Open"),
            _row("2026-09-02", "Continental Open", 90)]
    _write_scrape_csv(csv_path, rows)
    before = csv_path.read_text()

    class Boom(Exception):
        pass

    def explode(self, rowdicts):
        raise Boom("simulated serialization failure")

    monkeypatch.setattr(csv.DictWriter, "writerows", explode)

    with pytest.raises(Boom):
        backfill.merge_backfill(str(csv_path), [], dry_run=False)

    assert csv_path.read_text() == before
    assert not (tmp_path / "daily_scrape.csv.tmp").exists()


def test_dry_run_writes_nothing(tmp_path):
    csv_path = tmp_path / "daily_scrape.csv"
    _write_scrape_csv(csv_path, [_row("2026-09-01", "Southern Open")])
    before = csv_path.read_text()

    backfill.merge_backfill(str(csv_path),
                            [_row("2026-09-02", "Continental Open")],
                            dry_run=True)

    assert csv_path.read_text() == before


# ── PII ignore rules ──────────────────────────────────────────────────────

# Every output/input filename HOTEL_AUDIT_README.md tells an operator to
# produce, plus the tool's own default shape.
PII_PATHS = [
    "worldopen_audit.xlsx",
    "export.csv",
    "export_2026.csv",
    "hotel_audit_CCA_SO26.xlsx",
    "hotel_audit_out/hotel_audit_CCA_WO26.xlsx",
    "southern_open_audit.xlsx",
]


@pytest.mark.parametrize("path", PII_PATHS)
def test_hotel_audit_artifacts_are_gitignored(path):
    """git itself must refuse these, whatever .gitignore looks like."""
    r = subprocess.run(["git", "check-ignore", "-q", path],
                       cwd=REPO, capture_output=True)
    assert r.returncode == 0, (
        f"{path} is NOT gitignored — hotel-audit PII can reach a public repo")


def test_ignore_rules_hide_no_tracked_file():
    """The broad *.xlsx / export*.csv rules must not shadow tracked content."""
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO,
                             capture_output=True, text=True).stdout.split()
    shadowed = [p for p in tracked
                if subprocess.run(["git", "check-ignore", "-q", p],
                                  cwd=REPO, capture_output=True).returncode == 0]
    assert shadowed == [], f"ignore rules now shadow tracked files: {shadowed}"


def test_hotel_audit_default_output_stays_out_of_the_repo_root():
    """The default -o path must land in the gitignored directory."""
    src = (REPO / "hotel_audit.py").read_text()
    assert "hotel_audit_out" in src, (
        "hotel_audit.py no longer defaults its output into hotel_audit_out/")
