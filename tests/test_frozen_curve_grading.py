"""
Tests for the frozen-curve grading gate (audit v3 T1).

Grading compares a prediction made from a point on the daily curve against the
tournament's final_count. That is a fair test only when both numbers describe
the same event. When a registration export goes stale, the curve freezes at a
fraction of the final while reconcile_final_counts bumps final_count to the true
scraped total, and the model gets charged for the gap between two unrelated
numbers.

Two 2026 events sat in that state (Chicago Class, curve ~0.32x of a 288 final;
Pittsburgh Open, ~0.30x of 170), each recording ~40% T-3 errors and between them
dragging the published headline grade from C to D.
"""
import os
import sys
from importlib import import_module

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

m04e = import_module("04e_performance_data")


def curve(counts):
    """Daily frame for one tid from a list of cumulative counts."""
    return pd.DataFrame([
        {"tid": 1, "T": 30 - i * 5, "cum_regs": c} for i, c in enumerate(counts)
    ])


def test_healthy_curve_is_gradeable():
    """A curve that reaches its final count grades normally."""
    ok, ratio = m04e.is_curve_gradeable(curve([50, 120, 180, 200]), final=200)
    assert ok is True
    assert ratio == 1.0


def test_curve_slightly_under_final_is_still_gradeable():
    """Walk-ins mean the curve legitimately stops a little short of the final;
    that is a real model target, not a frozen export."""
    ok, ratio = m04e.is_curve_gradeable(curve([50, 120, 180, 194]), final=200)
    assert ok is True
    assert 0.96 < ratio < 0.98


def test_frozen_curve_is_excluded():
    """The Chicago Class shape: curve peaks at ~32% of the reconciled final."""
    ok, ratio = m04e.is_curve_gradeable(curve([20, 60, 92]), final=288)
    assert ok is False
    assert 0.31 < ratio < 0.33


def test_pittsburgh_shape_is_excluded():
    ok, ratio = m04e.is_curve_gradeable(curve([15, 35, 51]), final=170)
    assert ok is False
    assert 0.29 < ratio < 0.31


def test_walkin_shortfall_events_stay_gradeable():
    """The healthy 2026 events peak at 84-89% of final because walk-ins never
    reach the registration export. They are real model targets and must keep
    counting toward the grade — a threshold set at the walk-in boundary would
    have discarded five sound events alongside the two frozen ones."""
    for peak in (84, 86, 89):
        ok, _ = m04e.is_curve_gradeable(curve([40, peak]), final=100)
        assert ok is True, f"walk-in shortfall at {peak}% wrongly excluded"


def test_boundary_at_min_ratio_is_gradeable():
    """Exactly at the threshold counts as gradeable — the gate excludes only
    curves that fall below it."""
    ok, _ = m04e.is_curve_gradeable(curve([30, 60]), final=100)
    assert ok is True


def test_just_below_boundary_is_excluded():
    ok, _ = m04e.is_curve_gradeable(curve([30, 59]), final=100)
    assert ok is False


def test_empty_curve_is_not_gradeable():
    ok, ratio = m04e.is_curve_gradeable(curve([]), final=100)
    assert ok is False
    assert ratio == 0.0


def test_zero_or_missing_final_is_not_gradeable():
    assert m04e.is_curve_gradeable(curve([10, 20]), final=0)[0] is False
    assert m04e.is_curve_gradeable(curve([10, 20]), final=None)[0] is False


def test_evaluate_tournaments_records_frozen_exclusions():
    """The gate must report what it dropped: a silent exclusion from a published
    grade is indistinguishable from cherry-picking that grade upward."""
    daily = pd.DataFrame([
        {"tid": 7, "T": 30, "cum_regs": 20},
        {"tid": 7, "T": 10, "cum_regs": 92},
    ])
    skipped = []
    out = m04e.evaluate_tournaments(
        model=None,
        test_tournaments=[{
            "family": "Chicago Class", "tid": 7, "final_count": 288,
            "tournament_name": "2026 Chicago Class", "event_start": "2026-05-01",
        }],
        daily=daily,
        frozen_skipped=skipped,
    )
    assert out == []
    assert len(skipped) == 1
    name, final, ratio = skipped[0]
    assert name == "2026 Chicago Class"
    assert final == 288
    assert 0.31 < ratio < 0.33
