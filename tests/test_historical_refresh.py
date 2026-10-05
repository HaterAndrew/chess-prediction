"""scrape_historical.py --full: a full refresh writes outside output/ and
reports what changed against historical_tournaments.csv."""
import argparse
import os

import pytest

from scrapers.historical import _out_path
from scrapers.historical_output import FIELDNAMES, by_edition, refresh_diff
from shared.paths import OUTPUT_DIR


def _row(name, year, **values):
    return dict.fromkeys(FIELDNAMES, "") | {"tournament_name": name, "year": year} | values


def test_diff_ignores_how_a_resumed_run_wrote_blanks_and_counts():
    old = by_edition([_row("2025 Eastern Open", "2025", unique_states="12.0", rating_std="nan")])
    new = by_edition([_row("2025 Eastern Open", "2025", unique_states="12", rating_std="")])
    assert refresh_diff(old, new) == ([], [], {})


def test_diff_lists_added_removed_and_changed_columns():
    old = by_edition([_row("2024 World Open", "2024", total_entries="1000"),
                      _row("2019 Gone Open", "2019")])
    new = by_edition([_row("2024 World Open", "2024", total_entries="1012"),
                      _row("2026 New Open", "2026")])
    added, removed, changed = refresh_diff(old, new)
    assert added == [("2026 New Open", "2026")]
    assert removed == [("2019 Gone Open", "2019")]
    assert changed == {("2024 World Open", "2024"): ["total_entries"]}


def _args(full, out):
    return argparse.Namespace(full=full, out=out)


def test_full_refresh_must_write_outside_output(tmp_path):
    parser = argparse.ArgumentParser()
    assert _out_path(_args(True, str(tmp_path / "h.csv")), parser) == str(tmp_path / "h.csv")
    with pytest.raises(SystemExit):
        _out_path(_args(True, None), parser)
    with pytest.raises(SystemExit):
        _out_path(_args(True, os.path.join(OUTPUT_DIR, "h.csv")), parser)
    with pytest.raises(SystemExit):
        _out_path(_args(False, str(tmp_path / "h.csv")), parser)
    assert _out_path(_args(False, None), parser) == os.path.join(OUTPUT_DIR, "historical_tournaments.csv")
