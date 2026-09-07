"""Proper scoring rules and calibration diagnostics for interval forecasts.

Why this exists (2026-09-07 review): the model publishes 80% intervals but was
graded on MAE plus coverage alone. That pair is gameable in one direction —
widening every interval raises coverage and leaves MAE untouched — so it cannot
say whether an interval is well calibrated or merely large. The standard
instruments for interval forecasts are the pinball (quantile) loss and the
interval score of Gneiting and Raftery (2007), which charge for width and for
misses in the same currency, and a PIT histogram, which shows whether the
misses run one-tailed.

Everything here is a pure function from numbers to numbers. No I/O, no config,
no reading of OUTPUT_DIR: perf.evaluation and perf.report own that.

Convention: every score is negatively oriented (lower is better) and carries
the units of the quantity being predicted (entries), except `pit_value` and the
percentage helpers.
"""

import numpy as np
from scipy import stats

# The published interval is a central 80% interval, so alpha = 0.20 and the two
# quantile levels are 0.10 and 0.90.
DEFAULT_ALPHA = 0.20


def quantile_levels(alpha=DEFAULT_ALPHA):
    """The (lower, upper) quantile levels a central 1-alpha interval targets."""
    return alpha / 2.0, 1.0 - alpha / 2.0


def pinball_loss(actual, predicted, tau):
    """Quantile (pinball) loss at level tau. Lower is better.

    L(y, q) = tau * (y - q)        when y >= q
            = (1 - tau) * (q - y)  when y <  q

    Minimised in expectation by the true tau-quantile, which is what makes it
    the right charge for one arm of an interval: predicting the 0.9 quantile
    too low is penalised 9x harder than predicting it too high.
    """
    if not 0.0 < tau < 1.0:
        raise ValueError(f"tau must be in (0, 1), got {tau}")
    diff = actual - predicted
    return float(tau * diff if diff >= 0 else (1.0 - tau) * -diff)


def interval_score(actual, lo, hi, alpha=DEFAULT_ALPHA):
    """Gneiting-Raftery interval score for a central 1-alpha interval.

    IS = (hi - lo) + (2/alpha) * (lo - y) if y < lo
                   + (2/alpha) * (y - hi) if y > hi

    Lower is better. The first term charges for width, so an interval cannot buy
    coverage for free; the penalty terms charge for a miss in proportion to how
    far outside it landed. At alpha=0.20 a miss costs 10x the distance by which
    it missed, which is why widening only pays when it actually prevents misses.

    Equals 2/alpha times the sum of the pinball losses at the two quantile
    levels, which `test_interval_score_matches_pinball_identity` pins.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if hi < lo:
        raise ValueError(f"hi ({hi}) is below lo ({lo})")
    width = hi - lo
    penalty = 0.0
    if actual < lo:
        penalty = (2.0 / alpha) * (lo - actual)
    elif actual > hi:
        penalty = (2.0 / alpha) * (actual - hi)
    return float(width + penalty)


def scaled_interval_score(actual, lo, hi, alpha=DEFAULT_ALPHA):
    """Interval score as a fraction of the actual, so horizons compare.

    Raw interval score scales with tournament size: a 40-entry miss on a
    1,100-entry World Open is not the same error as on a 90-entry open. The
    graded corpus spans both, so the aggregate needs a scale-free version for
    the same reason the existing table reports MAE as a percentage.
    """
    if actual <= 0:
        raise ValueError(f"actual must be positive, got {actual}")
    return interval_score(actual, lo, hi, alpha) / float(actual) * 100.0


def pit_value(actual, point, lo, hi, alpha=DEFAULT_ALPHA):
    """Probability integral transform of `actual` under the published interval.

    The model's interval is lognormal in shape and asymmetric by construction:
    model.ci_floors scales the two arms independently, so the upper arm is
    legitimately longer. Fitting one sigma across both would read that intended
    skew as miscalibration, so this recovers a two-piece (split) lognormal: the
    arm below the point gets its own sigma, the arm above gets another, and each
    side contributes half the probability mass.

    Returns a value in [0, 1]. Under a well-calibrated model these are uniform;
    a histogram that piles up at both ends means intervals are too narrow, and
    one that leans to a single end means the point estimate is biased.
    """
    if min(actual, point, lo, hi) <= 0:
        raise ValueError("pit_value needs positive counts (lognormal support)")
    if not lo <= point <= hi:
        raise ValueError(f"point {point} outside [{lo}, {hi}]")

    z = stats.norm.ppf(1.0 - alpha / 2.0)
    log_actual = np.log(actual)
    log_point = np.log(point)
    sigma_lo = (log_point - np.log(lo)) / z
    sigma_hi = (np.log(hi) - log_point) / z

    # A degenerate arm (zero width) means the model claimed certainty on that
    # side; anything beyond it is a total miss for that tail.
    if log_actual < log_point:
        if sigma_lo <= 0:
            return 0.0
        return float(stats.norm.cdf((log_actual - log_point) / sigma_lo))
    if sigma_hi <= 0:
        return 1.0
    return float(stats.norm.cdf((log_actual - log_point) / sigma_hi))


def pit_histogram(pit_values, bins=10):
    """Bin PIT values into equal-width buckets over [0, 1].

    Returns {'bins': n, 'counts': [...], 'n': total, 'uniformity_chi2': x}.
    A perfectly calibrated model puts n/bins in every bucket; the chi-square
    statistic against that expectation is reported so the About tab can say how
    far off it is without re-deriving it in JavaScript.
    """
    vals = [v for v in pit_values if v is not None and np.isfinite(v)]
    if not vals:
        return {"bins": bins, "counts": [0] * bins, "n": 0, "uniformity_chi2": None}
    counts, _ = np.histogram(np.clip(vals, 0.0, 1.0), bins=bins, range=(0.0, 1.0))
    expected = len(vals) / bins
    chi2 = float(np.sum((counts - expected) ** 2 / expected)) if expected > 0 else None
    return {
        "bins": bins,
        "counts": [int(c) for c in counts],
        "n": len(vals),
        "uniformity_chi2": round(chi2, 2) if chi2 is not None else None,
    }


# ── Naive baselines ─────────────────────────────────────────────────────────
#
# The site reports "MAE 9.9%" with nothing to compare it against, so a reader
# cannot tell the model's margin over doing nothing. These are the two obvious
# do-nothing forecasts, scored through the same path as the model.


def baseline_last_year(family_history):
    """Predict this edition's final as the family's most recent prior final.

    `family_history` is an iterable of (year, final_count) for editions strictly
    before the one being predicted. Returns None when there is no history, which
    the caller must treat as "no baseline for this tournament" rather than zero.
    """
    hist = [(int(y), float(c)) for y, c in family_history
            if c is not None and np.isfinite(c) and c > 0]
    if not hist:
        return None
    return max(hist, key=lambda yc: yc[0])[1]


def baseline_current_ratio(count_at_T, global_median_ratio):
    """Predict final as today's count times the corpus-wide median ratio at T.

    This is the ratio model stripped of everything that makes it a model: no
    family history, no regression leg, no recalibration, no walk-ins. It is the
    number to beat before any of that machinery earns its place.
    """
    if count_at_T is None or count_at_T <= 0:
        return None
    if global_median_ratio is None or not np.isfinite(global_median_ratio):
        return None
    return float(count_at_T) * float(global_median_ratio)


def abs_pct_error(actual, predicted):
    """|predicted - actual| / actual as a percentage."""
    if actual <= 0:
        raise ValueError(f"actual must be positive, got {actual}")
    return abs(float(predicted) - float(actual)) / float(actual) * 100.0


def summarize(records, alpha=DEFAULT_ALPHA):
    """Aggregate per-prediction records into the block perf/report.py publishes.

    Each record is a dict with actual/point and, for interval-bearing forecasts,
    lo/hi. Records missing lo/hi (the baselines) are scored on point accuracy
    only and reported with interval fields set to None, so a baseline can never
    look better than the model by silently skipping the width charge.
    """
    apes, iscores, pits, pinball_lo, pinball_hi = [], [], [], [], []
    tau_lo, tau_hi = quantile_levels(alpha)

    for r in records:
        actual, point = r.get("actual"), r.get("point")
        if actual is None or point is None or actual <= 0 or point <= 0:
            continue
        apes.append(abs_pct_error(actual, point))
        lo, hi = r.get("lo"), r.get("hi")
        if lo is None or hi is None or lo <= 0 or hi < lo:
            continue
        iscores.append(scaled_interval_score(actual, lo, hi, alpha))
        pinball_lo.append(pinball_loss(actual, lo, tau_lo))
        pinball_hi.append(pinball_loss(actual, hi, tau_hi))
        if lo <= point <= hi:
            pits.append(pit_value(actual, point, lo, hi, alpha))

    if not apes:
        return None
    out = {
        "n": len(apes),
        "mae_pct": round(float(np.mean(apes)), 1),
        "median_ape_pct": round(float(np.median(apes)), 1),
    }
    if iscores:
        out.update({
            "n_interval": len(iscores),
            "interval_score_pct": round(float(np.mean(iscores)), 1),
            "pinball_lo": round(float(np.mean(pinball_lo)), 2),
            "pinball_hi": round(float(np.mean(pinball_hi)), 2),
            "pit": pit_histogram(pits),
        })
    else:
        out.update({
            "n_interval": 0,
            "interval_score_pct": None,
            "pinball_lo": None,
            "pinball_hi": None,
            "pit": None,
        })
    return out
