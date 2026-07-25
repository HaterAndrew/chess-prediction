"""
Tests for docs/daily_series.js — the browser-side gap-safe daily_data reader.

Audit v3 P1 (audit/AUDIT_2026-07-25.md). The front end read daily_data by array
position, so a missing scrape day was rendered as a single day's registrations
("+125 entries yesterday" on Bradley Open, against a real 197-entry event). The
pipeline fix stops the corrupt values reaching the client; these tests pin the
client-side defence so the next missing day cannot be mislabelled either.

Runs the module under node and asserts on its JSON output. Skipped when node is
unavailable, matching test_audit_js_parity.py.
"""
import json
import os
import shutil
import subprocess

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(PROJECT_DIR, "tests", "js", "daily_series_driver.js")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available")


@pytest.fixture(scope="module")
def res():
    proc = subprocess.run(["node", DRIVER], capture_output=True, text=True,
                          cwd=PROJECT_DIR, timeout=60)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_incident_point_above_current_count_is_dropped(res):
    """The 625 reading on a 197-entry event is impossible and must not draw."""
    pts = res["incident_sanitized"]["points"]
    assert all(p[1] <= 197 for p in pts), f"impossible point survived: {pts}"
    assert res["incident_sanitized"]["capped"] is True
    assert res["incident_sanitized"]["dropped"] >= 1


def test_incident_tail_is_flagged_suspect(res):
    assert res["incident_suspect"] is True


def test_incident_produces_no_bogus_daily_change(res):
    """With the impossible point dropped, there is no one-day interval left to
    report, so the chip must return null rather than inventing '+125 today'."""
    assert res["incident_latest_daily"] is None


def test_healthy_card_reports_real_daily_change(res):
    """Contiguous data still works: 200 - 140 == 60 on the last single day."""
    assert res["healthy_latest_daily"] == 60


def test_healthy_intervals_are_single_day_and_dated(res):
    ivs = res["healthy_intervals"]
    assert [i["span"] for i in ivs] == [1, 1, 1]
    assert all(i["isGap"] is False for i in ivs)
    assert [i["date"] for i in ivs] == ["2026-07-02", "2026-07-03", "2026-07-04"]


def test_multi_day_gap_is_not_reported_as_one_day(res):
    """The core P1 regression: a 7-day gap adding 220 entries must not be
    labelled as a single day's registrations."""
    assert res["gappy_latest_daily"] is None
    iv = res["gappy_latest_interval"]
    assert iv["span"] == 7
    assert iv["added"] == 220
    assert iv["isGap"] is True
    assert abs(iv["perDay"] - 220 / 7) < 1e-9


def test_messy_series_is_sorted_deduped_and_filtered(res):
    pts = res["messy_sanitized"]["points"]
    days = [p[0] for p in pts]
    assert days == sorted(days), "points not sorted by day index"
    assert len(days) == len(set(days)), "duplicate day index survived"
    assert all(d >= 0 for d in days), "negative day index survived"
    counts = [p[1] for p in pts]
    assert counts == sorted(counts), "non-monotone point survived"


def test_dates_derive_from_day_index_not_array_position(res):
    assert res["date_day0"] == "2026-07-01"
    # day 8 of a card anchored at 2026-07-01, even though it is only the
    # third element in the array.
    assert res["date_day8"] == "2026-07-09"


def test_missing_anchor_returns_null_rather_than_guessing(res):
    assert res["date_no_anchor"] is None


def test_empty_and_null_inputs_are_safe(res):
    assert res["empty_sanitized"]["points"] == []
    assert res["null_sanitized"]["points"] == []
    assert res["empty_latest"] is None
