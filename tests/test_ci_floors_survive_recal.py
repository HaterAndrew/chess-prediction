"""
Tests for CI floor survival across recalibration (audit v3 N3).

predict_nowcast sets several floors on the confidence interval — growth headroom
for families with no history, a widened upper bound for blitz events, and a
minimum CI width at short horizons. Those floors used to be applied once, above
the recalibration block. Recal then rebuilt the interval symmetrically in log
space around its own bias-corrected centre, which discarded every one of them: a
0-edition family's min_upper of 375 came back out at ~113.

The families those floors protect are exactly the ones whose point estimate is
least trustworthy, so collapsing their upper bound is backwards. These tests pin
that the floors still bind after recal, and that the interval keeps the
lognormal skew rather than being symmetrised.
"""
import os
import sys
from importlib import import_module

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

m04c = import_module("04c_final_model")


def _model_with_recal(bias=0.75, ci_adj=0.5):
    """A model carrying recal factors that would previously have flattened the
    CI: a downward bias correction plus an aggressive CI shrink."""
    model = m04c.N5v4_Final()
    model._recal_bias = {1: bias, 3: bias, 7: bias, 14: bias, 28: bias}
    model._recal_ci = {1: ci_adj, 3: ci_adj, 7: ci_adj, 14: ci_adj, 28: ci_adj}
    return model


def test_min_ci_width_floor_survives_recal():
    """At T<=3 the interval must stay at least +/-5% of the point estimate even
    when recal asks for a 0.5x CI shrink.

    current_count is kept well below the point estimate so the minimum-width
    rule is the binding constraint. (When current_count approaches the point the
    lower bound is deliberately pinned to it instead — entries already taken
    cannot un-register, so a narrow lower arm there is correct, not a collapse;
    test_lower_bound_pinned_to_current_count covers that case.)
    """
    model = _model_with_recal()
    p, lo, hi = _run_floors(model, 200.0, 190.0, 212.0, days_remaining=3,
                            current_count=50, n_editions=5)
    assert hi - p >= p * 0.05 - 1, f"upper arm collapsed: point={p} high={hi}"
    assert p - lo >= p * 0.05 - 1, f"lower arm collapsed: point={p} low={lo}"


def test_lower_bound_pinned_to_current_count():
    """The CI lower bound never drops below entries already registered."""
    model = _model_with_recal(bias=0.75)
    p, lo, hi = _run_floors(model, 200.0, 190.0, 212.0, days_remaining=3,
                            current_count=150, n_editions=5)
    assert lo >= 150, f"lower bound {lo} below the 150 entries already in"
    assert p >= 150


def test_zero_edition_upper_floor_survives_recal():
    """A 0-edition family at T-30 with 15 entries gets min_upper = 25x count =
    375. Recal must not be able to pull the published upper bound below it."""
    model = _model_with_recal()
    p, lo, hi = _run_floors(model, 60.0, 40.0, 90.0, days_remaining=30,
                            current_count=15, n_editions=0)
    assert hi >= 375 - 1, f"0-edition growth headroom lost: high={hi} (want >=375)"


def test_blitz_upper_floor_survives_recal():
    """Blitz events surge on the day; the upper bound floor is 4x the current
    count at T-1 and must outlive a CI-shrinking recal."""
    model = _model_with_recal()
    p, lo, hi = _run_floors(model, 120.0, 110.0, 130.0, days_remaining=1,
                            current_count=100, n_editions=5, is_blitz=True)
    assert hi >= 400 - 1, f"blitz headroom lost: high={hi} (want >=400)"


def test_recal_preserves_asymmetric_arms():
    """A lognormal interval has a longer upper arm. Scaling each arm by the same
    factor keeps that; the old symmetric rebuild averaged them away."""
    model = _model_with_recal(bias=1.0, ci_adj=1.0)
    p, lo, hi = _run_floors(model, 200.0, 180.0, 260.0, days_remaining=30,
                            current_count=100, n_editions=5)
    upper_arm, lower_arm = hi - p, p - lo
    assert upper_arm > lower_arm, (
        f"skew lost — arms symmetrised: point={p} low={lo} high={hi}")


def test_point_never_below_current_count():
    """The existing floor: a prediction cannot fall below entries already in."""
    model = _model_with_recal(bias=0.5)
    p, lo, hi = _run_floors(model, 120.0, 100.0, 140.0, days_remaining=3,
                            current_count=180, n_editions=5)
    assert p >= 180, f"point {p} below current_count 180"
    assert hi >= p


def _run_floors(model, point, low, high, days_remaining, current_count,
                n_editions, is_blitz=False):
    """Drive the floor + recal tail of predict_nowcast directly.

    predict_nowcast's front half needs a fitted ratio model; this exercises the
    CI-bounds half in isolation via the same helper the method defines.
    """
    return m04c._predict_nowcast_ci_tail(
        model, point, low, high,
        days_remaining=days_remaining, current_count=current_count,
        n_editions=n_editions, is_blitz=is_blitz)
