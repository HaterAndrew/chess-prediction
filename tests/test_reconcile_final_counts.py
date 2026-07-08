"""Regression tests for reconcile_final_counts.

Covers the two jobs the module does when the manual CCA export is absent (every
CI run):
  1. Bump an existing event's final_count up to the live daily_scrape peak so the
     04e freshness guard doesn't abort on stale early-registration truth labels.
  2. (H2) Append a roster-pending skeleton for a *scraped* event that has no
     summary row yet, so a 2026 tournament whose registration opened after the
     last export is no longer invisible to the whole pipeline. The skeleton
     carries has_timestamps=False so every 04c/04e training/grading filter
     excludes it until a real export supplies per-registration timestamps.
"""
import os
import sys

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from reconcile_final_counts import reconcile_final_counts  # noqa: E402


def _summary(out):
    return pd.read_csv(os.path.join(out, "tournament_summary.csv"))


def test_bumps_existing_final_count_to_scrape_peak(tmp_output):
    """Atlantic City Open is in both summary and scrape; if the scrape peak
    exceeds the frozen final_count it is raised to the peak (gross semantics)."""
    before = _summary(tmp_output)
    ac_before = int(before.loc[before["tournament_name"] == "2026 Atlantic City Open",
                               "final_count"].iloc[0])
    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    ac_after = int(after.loc[after["tournament_name"] == "2026 Atlantic City Open",
                             "final_count"].iloc[0])
    # scrape peak for Atlantic City is 225; final_count is raised to at least that
    # (never lowered below the frozen snapshot).
    assert ac_after >= ac_before
    assert ac_after == max(ac_before, 225)


def test_appends_roster_pending_for_unknown_scrape_event(tmp_output):
    """H2: DC International and Hartford are scraped but absent from summary.
    Reconcile must append skeleton rows for them, not silently drop them."""
    before = set(_summary(tmp_output)["tournament_name"])
    assert "2026 Hartford Open" not in before
    assert "2026 DC International" not in before

    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    names = set(after["tournament_name"])
    assert "2026 Hartford Open" in names
    assert "2026 DC International" in names

    hartford = after.loc[after["tournament_name"] == "2026 Hartford Open"].iloc[0]
    # final_count is the gross scrape peak (5 in the fixture)
    assert int(hartford["final_count"]) == 5
    assert int(hartford["tournament_year"]) == 2026
    assert hartford["family"] == "Hartford Open"
    # The load-bearing safety flag: no timestamps => excluded from every
    # 04c/04e training and grading filter until a real export arrives.
    assert bool(hartford["has_timestamps"]) is False
    assert bool(hartford["roster_pending"]) is True


def test_appended_tids_are_unique(tmp_output):
    """Skeleton rows get fresh tids above the existing max so nothing collides."""
    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    assert after["tid"].is_unique


def test_existing_rows_marked_not_roster_pending(tmp_output):
    """When the roster_pending column is introduced, pre-existing rows default to
    False, never NaN/True — they are real roster entries."""
    reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    real = after.loc[after["tournament_name"] == "2026 Atlantic City Open"].iloc[0]
    assert bool(real["roster_pending"]) is False


def test_no_scrape_file_is_noop(tmp_output):
    """Missing daily_scrape.csv => return 0, summary untouched (safe to call
    blindly in the export-present branch)."""
    os.remove(os.path.join(tmp_output, "daily_scrape.csv"))
    before = _summary(tmp_output)
    n = reconcile_final_counts(tmp_output, verbose=False)
    after = _summary(tmp_output)
    assert n == 0
    pd.testing.assert_frame_equal(before, after)


def test_return_counts_bumped_plus_appended(tmp_output):
    """Return value is the total number of tournaments changed (raised OR
    appended), not just the bumped ones."""
    n = reconcile_final_counts(tmp_output, verbose=False)
    # At least the 2 appended (Hartford, DC International); Atlantic City may also
    # bump depending on the frozen snapshot, so assert the appended floor.
    assert n >= 2
