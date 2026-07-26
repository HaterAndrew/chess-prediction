"""v4 X1 (audit/AUDIT_2026-07-26.md): the interim-card pace gate.

First direct test of 04d's prediction gating (G4). The logic lives in
pipeline_utils.pace_gate_ok because importing 04d executes its whole
pipeline at module level; 04d calls the same function.

Contract: the pre-0e1c6a1 behaviour (10+ registrations inside 45 days) is
preserved exactly; the 46-90 day extension exists only where the family
curve says the ratio carries signal (curve share >= PACE_MIN_CURVE_PCT);
nothing fires beyond 90 days or under 10 registrations.
"""

from pipeline_utils import PACE_MIN_CURVE_PCT, curve_pct_at, pace_gate_ok

# A realistic slow-filling family: ~1.2% cumulative at T-90, 10% at T-42.
SLOW_CURVE = {120: 0.005, 90: 0.012, 75: 0.019, 42: 0.10, 14: 0.55, 0: 1.0}
# A fast-filling family that clears the floor well before 45 days.
FAST_CURVE = {90: 0.06, 42: 0.30, 14: 0.75, 0: 1.0}


def test_under_10_registrations_never_fires():
    assert not pace_gate_ok(9, 10, FAST_CURVE)
    assert not pace_gate_ok(0, 3, FAST_CURVE)


def test_legacy_45_day_gate_preserved_regardless_of_curve():
    # Inside 45 days the old gate fired on count alone; an empty or slow
    # curve must not regress that.
    assert pace_gate_ok(10, 45, {})
    assert pace_gate_ok(10, 45, SLOW_CURVE)
    assert pace_gate_ok(10, 1, {})


def test_extension_denied_where_curve_share_is_noise():
    # The X1 defect: 46-90 days out on a typical curve, the ratio scale-up
    # pinned the clamp ceiling. The gate must fall back to historical avg.
    assert not pace_gate_ok(50, 75, SLOW_CURVE)
    assert not pace_gate_ok(500, 90, SLOW_CURVE)


def test_extension_granted_where_curve_carries_signal():
    assert pace_gate_ok(10, 60, FAST_CURVE)
    assert pace_gate_ok(10, 90, FAST_CURVE)


def test_beyond_90_days_never_fires():
    assert not pace_gate_ok(1000, 91, FAST_CURVE)


def test_unknown_curve_fails_conservative_in_extension():
    assert not pace_gate_ok(50, 60, {})
    assert not pace_gate_ok(50, 60, None)


def test_curve_pct_interpolation():
    # Exact grid point: returned as-is (modulo float arithmetic).
    assert abs(curve_pct_at(SLOW_CURVE, 75) - 0.019) < 1e-9
    # Between grid points: linear. 60 sits 18/33 of the way from 42 to 75.
    expect = 0.10 + (0.019 - 0.10) * (60 - 42) / (75 - 42)
    assert abs(curve_pct_at(SLOW_CURVE, 60) - expect) < 1e-9
    # Outside the grid: clamped to the nearest endpoint.
    assert curve_pct_at(SLOW_CURVE, 200) == 0.005
    assert curve_pct_at(SLOW_CURVE, -1) == 1.0
    assert curve_pct_at({}, 30) == 0.0


def test_floor_is_the_documented_constant():
    # Exactly at the floor passes; a hair under fails.
    at_floor = {60: PACE_MIN_CURVE_PCT}
    under = {60: PACE_MIN_CURVE_PCT - 1e-6}
    assert pace_gate_ok(10, 60, at_floor)
    assert not pace_gate_ok(10, 60, under)
