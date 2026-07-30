"""CI floor + nowcast CI tail (04c lines 84-198, verbatim)."""

import numpy as np

def apply_ci_floors(point, low, high, days_remaining, current_count,
                    n_editions, is_blitz=False):
    """Apply every floor/cap the published confidence interval must satisfy.

    Idempotent by construction — each rule is a max/min against a bound derived
    from the current point, never a multiplicative widening — so it can be run
    both before and after recalibration.

    v3 N3 (audit/AUDIT_2026-07-25.md): these rules used to be inline in
    predict_nowcast, applied once, ABOVE the recalibration block. Recal then
    rebuilt the interval symmetrically in log space around its own bias-corrected
    centre, which discarded all of them: a 0-edition family's min_upper of 375
    came back out at ~113. The families these floors protect are precisely the
    ones whose point estimate is least trustworthy, so collapsing their upper
    bound is backwards.
    """
    if n_editions == 0:
        # Growth headroom for families with no history at all.
        if days_remaining >= 28 and current_count < 20:
            min_upper = current_count * 25
        elif days_remaining >= 28 and current_count < 80:
            min_upper = current_count * 8
        elif days_remaining >= 7 and current_count < 30:
            min_upper = current_count * 10
        elif days_remaining >= 7 and current_count < 100:
            min_upper = current_count * 4
        else:
            min_upper = high
        high = max(high, min_upper)
        high = min(high, max(point * 8.0, current_count * 30))
        low = max(low, point * 0.15)
    elif n_editions == 1:
        high = min(high, point * 3.0)
        low = max(low, point * 0.3)

    # Blitz events surge 2-4x on the day; the parametric model assumes gradual
    # registration and under-covers them.
    if is_blitz:
        if days_remaining <= 1:
            min_blitz_upper = current_count * 4.0
        elif days_remaining <= 3:
            min_blitz_upper = current_count * 5.0
        elif days_remaining <= 5:
            min_blitz_upper = current_count * 6.0
        elif days_remaining <= 7:
            min_blitz_upper = current_count * 5.0
        else:
            min_blitz_upper = 0
        if min_blitz_upper > 0:
            high = max(high, min_blitz_upper)

    # Minimum CI width: at very short T, LOO calibration on well-predicted
    # training data yields unrealistically tight intervals.
    if days_remaining <= 1:
        min_half = point * 0.06
    elif days_remaining <= 3:
        min_half = point * 0.05
    elif days_remaining <= 7:
        min_half = point * 0.04
    else:
        min_half = 0
    if min_half > 0:
        if high - point < min_half:
            high = point + min_half
        if point - low < min_half:
            low = point - min_half
    return point, low, high


def _predict_nowcast_ci_tail(model, point, low, high, days_remaining,
                             current_count, n_editions, is_blitz=False):
    """Floors, recalibration and the final rounding for predict_nowcast.

    Split out of the method so the v3 N3 behaviour — floors surviving recal, and
    recal preserving the interval's asymmetry — is directly testable without
    standing up a fitted ratio model. See tests/test_ci_floors_survive_recal.py.
    """
    point, low, high = apply_ci_floors(
        point, low, high, days_remaining, current_count, n_editions, is_blitz)

    # Apply recalibration corrections if available. The stage check goes through
    # the model's own accessor when it has one; this function is also called
    # directly from tests with a stub model that has no stage machinery, and
    # those must keep recal enabled.
    recal_on = getattr(model, '_stage_on', None)
    recal_on = recal_on('recal') if callable(recal_on) else True
    if recal_on and getattr(model, '_recal_bias', None):
        recal_Ts = sorted(model._recal_bias.keys())
        nearest_T = min(recal_Ts, key=lambda t: abs(t - days_remaining))
        bias_factor = model._recal_bias.get(nearest_T, 1.0)
        ci_adj = model._recal_ci.get(nearest_T, 1.0)
        center = point * bias_factor
        # v3 N3: scale each arm independently instead of rebuilding a symmetric
        # log interval about the centre. The distribution is lognormal, so its
        # upper arm is legitimately longer; the old form averaged the two arms
        # and handed back the mean half-width, collapsing the fitted skew.
        lo_arm_log = max(np.log(max(point, 1)) - np.log(max(low, 1)), 0) * ci_adj
        hi_arm_log = max(np.log(max(high, 1)) - np.log(max(point, 1)), 0) * ci_adj
        log_center = np.log(max(center, 1))
        low = np.exp(log_center - lo_arm_log)
        high = np.exp(log_center + hi_arm_log)
        point = center
        # Recal moved the centre, so bounds expressed as a ratio of the point
        # have to be recomputed against the new one.
        point, low, high = apply_ci_floors(
            point, low, high, days_remaining, current_count, n_editions, is_blitz)

    # Floor: point estimate must be >= current_count (can't un-register), but
    # the CI lower bound may sit below the point for honest uncertainty.
    point = round(max(point, current_count))
    low = round(max(low, current_count))
    high = round(max(high, point))
    return (point, low, high)


