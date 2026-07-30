"""Tests for docs/util_core.js — the shared date/curve/pace/staleness helpers.

C1 of the app.js split. These helpers feed every renderer (hero, milestones,
delta banner, staleness banner), so they get the same node-driver treatment as
daily_series: run the real file under node, assert on its JSON output. Skipped
when node is unavailable, matching test_daily_series_js.py.
"""
import json
import os
import shutil
import subprocess

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(PROJECT_DIR, "tests", "js", "util_core_driver.js")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available")


@pytest.fixture(scope="module")
def res():
    proc = subprocess.run(["node", DRIVER], capture_output=True, text=True,
                          cwd=PROJECT_DIR, timeout=60)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_fmt_and_isdone(res):
    assert res["fmt_null"] == "–"
    assert res["fmt_num"] == "12,345"
    assert res["isdone_complete"] is True
    assert res["isdone_historical"] is True
    assert res["isdone_live"] is False


def test_date_arithmetic_is_local_midnight(res):
    assert res["days_between"] == 30
    assert res["add_days"] == [2026, 7, 31]
    assert res["fmt_date_empty"] == "–"
    assert res["fmt_datetime_bad"] == "–"


def test_curve_interpolation_and_clamps(res):
    """Outside the curve's span the endpoints clamp; inside it interpolates."""
    assert res["interp_above"] == pytest.approx(0.10)
    assert res["interp_below"] == pytest.approx(1.0)
    assert res["interp_mid"] == pytest.approx(0.30)
    assert res["interp_empty"] == 1


def test_early_bird_requires_hike_and_gap(res):
    """A 3-day-out price step is a late-registration penalty, not an early
    bird; equal fees are no early bird at all (EARLY_BIRD_MIN_GAP_DAYS)."""
    assert res["eb_valid"] is True
    assert res["eb_short_gap"] is False
    assert res["eb_no_hike"] is False
    assert res["eb_missing_fields"] is False


def test_freshness_age_overrules_the_baked_flag(res):
    """Audit v3 P2: a mid-run crash leaves is_stale=false in place; the
    browser clock is the one signal a broken pipeline cannot forge."""
    aged = res["aged_out"]
    assert aged["stale"] is True
    assert aged["reason"] == "age"
    assert aged["ageHours"] == pytest.approx(132.0)
    assert res["stale_after_hours"] == 36


def test_freshness_flag_and_degraded_paths(res):
    fresh = res["fresh"]
    assert fresh["stale"] is False and fresh["reason"] is None
    assert res["flagged"]["stale"] is True
    assert res["flagged"]["reason"] == "flagged"
    assert res["degraded"]["stale"] is True
    assert res["degraded"]["reason"] == "degraded"
    assert res["empty_freshness"]["stale"] is False
    assert res["empty_freshness"]["ageHours"] is None


def test_pace_alert_accessors(res):
    assert res["pace_alert"] == {"status": "above_pace"}
    assert res["pace_alert_none"] is None
    assert res["pace_badge_empty"] == ""
