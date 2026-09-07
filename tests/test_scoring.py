"""Tests for perf/scoring.py — proper scoring rules and PIT.

Pinball loss and the interval score both have closed forms, so these assert
against values computed by hand rather than against whatever the code happens
to return. The interval-score/pinball identity is pinned separately: it is the
property that makes the two instruments consistent, and an implementation can
satisfy each formula alone while disagreeing on the relationship.
"""
import math
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from perf.scoring import (  # noqa: E402
    DEFAULT_ALPHA, abs_pct_error, baseline_current_ratio, baseline_last_year,
    interval_score, pinball_loss, pit_histogram, pit_value, quantile_levels,
    scaled_interval_score, summarize)


# ── pinball loss ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("actual,pred,tau,expected", [
    # Under-predicting the 0.9 quantile is charged 9x over-predicting it.
    (100, 90, 0.9, 9.0),
    (80, 90, 0.9, 1.0),
    # Mirror image at the 0.1 quantile.
    (100, 90, 0.1, 1.0),
    (80, 90, 0.1, 9.0),
    # A perfect call costs nothing at any level.
    (100, 100, 0.5, 0.0),
    (100, 100, 0.9, 0.0),
])
def test_pinball_loss_hand_computed(actual, pred, tau, expected):
    assert pinball_loss(actual, pred, tau) == pytest.approx(expected)


def test_pinball_is_minimised_at_the_true_quantile():
    """The property that makes it a proper scoring rule.

    Sample from a known distribution and check the empirical loss bottoms out
    at that distribution's tau-quantile rather than at its mean or median.
    """
    import numpy as np
    rng = np.random.default_rng(0)
    sample = rng.normal(100, 15, 20000)
    tau = 0.9
    truth = float(np.quantile(sample, tau))
    at_truth = np.mean([pinball_loss(y, truth, tau) for y in sample])
    for offset in (-10, -4, 4, 10):
        worse = np.mean([pinball_loss(y, truth + offset, tau) for y in sample])
        assert worse > at_truth


def test_pinball_rejects_a_tau_outside_the_open_unit_interval():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            pinball_loss(100, 90, bad)


# ── interval score ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("actual,expected", [
    (100, 20.0),    # inside: width only
    (90, 20.0),     # exactly on the lower bound is still inside
    (110, 20.0),    # and on the upper bound
    (80, 120.0),    # 10 below: 20 + (2/0.2)*10
    (120, 120.0),   # 10 above, symmetric
])
def test_interval_score_hand_computed(actual, expected):
    assert interval_score(actual, 90, 110, alpha=0.2) == pytest.approx(expected)


def test_interval_score_matches_pinball_identity():
    """IS_alpha = (2/alpha) * [pinball(lo, alpha/2) + pinball(hi, 1-alpha/2)].

    Holds inside and outside the interval; this is what stops the two
    instruments from drifting apart.
    """
    alpha = DEFAULT_ALPHA
    tau_lo, tau_hi = quantile_levels(alpha)
    lo, hi = 90.0, 110.0
    for actual in (60, 80, 90, 100, 110, 130, 250):
        via_pinball = (2.0 / alpha) * (
            pinball_loss(actual, lo, tau_lo) + pinball_loss(actual, hi, tau_hi))
        assert interval_score(actual, lo, hi, alpha) == pytest.approx(via_pinball)


def test_widening_an_interval_is_not_free():
    """The defect that motivated this module.

    Under MAE-plus-coverage, doubling every interval improves coverage and
    leaves MAE untouched. The interval score has to charge for it.
    """
    tight = interval_score(100, 95, 105, alpha=0.2)
    wide = interval_score(100, 50, 150, alpha=0.2)
    assert wide > tight


def test_widening_still_pays_when_it_prevents_a_bad_miss():
    """It must not simply always prefer the narrower interval."""
    tight_miss = interval_score(200, 95, 105, alpha=0.2)
    wide_hit = interval_score(200, 50, 250, alpha=0.2)
    assert wide_hit < tight_miss


def test_interval_score_rejects_an_inverted_interval():
    with pytest.raises(ValueError):
        interval_score(100, 110, 90)


def test_scaled_interval_score_is_scale_free():
    """Same relative geometry on a small and a large event scores the same."""
    small = scaled_interval_score(100, 90, 110, alpha=0.2)
    large = scaled_interval_score(1000, 900, 1100, alpha=0.2)
    assert small == pytest.approx(large)


# ── PIT ─────────────────────────────────────────────────────────────────────

def test_pit_at_the_interval_bounds_equals_the_nominal_tail_mass():
    """The anchor: an 80% interval's bounds sit at PIT 0.10 and 0.90."""
    point, lo, hi = 100.0, 100 / 1.5, 100 * 1.5
    assert pit_value(lo, point, lo, hi) == pytest.approx(0.10, abs=1e-6)
    assert pit_value(hi, point, lo, hi) == pytest.approx(0.90, abs=1e-6)


def test_pit_at_the_point_estimate_is_one_half():
    assert pit_value(100, 100, 60, 180) == pytest.approx(0.5)


def test_pit_respects_an_asymmetric_interval():
    """model.ci_floors scales the two arms independently, so the published
    interval is skewed by design. A single-sigma PIT would read that intended
    skew as miscalibration; each arm gets its own sigma instead."""
    point, lo, hi = 100.0, 90.0, 200.0   # short lower arm, long upper arm
    assert pit_value(lo, point, lo, hi) == pytest.approx(0.10, abs=1e-6)
    assert pit_value(hi, point, lo, hi) == pytest.approx(0.90, abs=1e-6)
    # A value just under the point sits well below 0.5 because that arm is tight.
    assert pit_value(95, point, lo, hi) < 0.35


def test_pit_is_monotone_in_the_actual():
    point, lo, hi = 100.0, 70.0, 150.0
    seq = [pit_value(a, point, lo, hi) for a in (75, 85, 100, 120, 145)]
    assert seq == sorted(seq)


def test_pit_rejects_a_point_outside_its_own_interval():
    with pytest.raises(ValueError):
        pit_value(100, 200, 90, 110)


def test_pit_rejects_non_positive_counts():
    with pytest.raises(ValueError):
        pit_value(0, 100, 90, 110)


def test_pit_histogram_is_flat_for_a_calibrated_forecaster():
    """Uniform PIT values must produce near-equal buckets and a small chi2."""
    vals = [(i + 0.5) / 100 for i in range(100)]
    h = pit_histogram(vals, bins=10)
    assert h["n"] == 100
    assert h["counts"] == [10] * 10
    assert h["uniformity_chi2"] == pytest.approx(0.0)


def test_pit_histogram_flags_over_narrow_intervals():
    """Mass piled at both ends is the signature of intervals that are too tight."""
    vals = [0.01] * 40 + [0.99] * 40 + [0.5] * 20
    h = pit_histogram(vals, bins=10)
    assert h["counts"][0] == 40 and h["counts"][-1] == 40
    assert h["uniformity_chi2"] > 50


def test_pit_histogram_handles_an_empty_input():
    h = pit_histogram([], bins=10)
    assert h["n"] == 0 and h["uniformity_chi2"] is None


# ── baselines ───────────────────────────────────────────────────────────────

def test_last_year_baseline_takes_the_most_recent_prior_edition():
    assert baseline_last_year([(2022, 180), (2024, 210), (2023, 195)]) == 210


def test_last_year_baseline_returns_none_without_history():
    assert baseline_last_year([]) is None
    assert baseline_last_year([(2024, 0), (2023, None)]) is None


def test_current_ratio_baseline():
    assert baseline_current_ratio(100, 1.8) == pytest.approx(180.0)
    assert baseline_current_ratio(0, 1.8) is None
    assert baseline_current_ratio(100, None) is None
    assert baseline_current_ratio(100, float("nan")) is None


def test_abs_pct_error():
    assert abs_pct_error(200, 220) == pytest.approx(10.0)
    assert abs_pct_error(200, 180) == pytest.approx(10.0)
    with pytest.raises(ValueError):
        abs_pct_error(0, 100)


# ── summarize ───────────────────────────────────────────────────────────────

def test_summarize_reports_interval_metrics_when_bounds_are_present():
    recs = [
        {"actual": 100, "point": 105, "lo": 90, "hi": 120},
        {"actual": 200, "point": 190, "lo": 170, "hi": 230},
    ]
    out = summarize(recs)
    assert out["n"] == 2 and out["n_interval"] == 2
    assert out["interval_score_pct"] > 0
    assert out["pit"]["n"] == 2


def test_summarize_marks_a_point_only_forecast_as_having_no_interval():
    """A baseline must not look better by silently skipping the width charge."""
    recs = [{"actual": 100, "point": 105}, {"actual": 200, "point": 190}]
    out = summarize(recs)
    assert out["n"] == 2
    assert out["n_interval"] == 0
    assert out["interval_score_pct"] is None
    assert out["pit"] is None
    assert out["mae_pct"] == pytest.approx(5.0)


def test_summarize_returns_none_when_nothing_is_scoreable():
    assert summarize([]) is None
    assert summarize([{"actual": 0, "point": 10}]) is None


def test_summarize_skips_a_record_it_cannot_score_without_dropping_the_rest():
    recs = [
        {"actual": 100, "point": 110},
        {"actual": None, "point": 50},
        {"actual": 100, "point": 90},
    ]
    out = summarize(recs)
    assert out["n"] == 2
    assert out["mae_pct"] == pytest.approx(10.0)


def test_summarize_is_finite_on_a_total_miss():
    out = summarize([{"actual": 100, "point": 1000, "lo": 900, "hi": 1100}])
    assert math.isfinite(out["interval_score_pct"])
