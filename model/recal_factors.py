"""The factors recalibrate() fits from a horizon's residuals: pure arithmetic.

bias_fit gives the location correction, stationarity_of and recent_half_bias
the stationarity probe and its carryover refit, ci_scale the width that makes
the interval cover its target around the center the site publishes.
"""
import math

import numpy as np

from shared.pickup_blend import pickup_blend

# The bias factor never moves a point by more than this, either way.
BIAS_BOUNDS = (0.80, 1.20)


def trimmed_mean(errs):
    """IQR-trimmed mean (>2x IQR dropped), falling back to the raw mean below
    3 survivors — same rule the pooled path has always used."""
    errs = np.asarray(errs, dtype=float)
    q1, q3 = np.percentile(errs, [25, 75])
    iqr = q3 - q1
    m = (errs >= q1 - 2 * iqr) & (errs <= q3 + 2 * iqr)
    kept = errs[m]
    return float(np.mean(kept if len(kept) >= 3 else errs))


def bias_factor_of(mean_bias):
    """The multiplier that removes mean_bias, held to BIAS_BOUNDS."""
    return max(BIAS_BOUNDS[0], min(BIAS_BOUNDS[1], 1.0 / (1.0 + mean_bias)))


def bias_fit(records, regime_year, regime_min_n):
    """(mean_bias, bias_cohort): the location error the correction removes.

    v5 Cat L: bias is a REGIME (location) property. Production recal exists
    to correct predictions for the current year, and a pooled multi-year
    mean dilutes a current-regime shift toward 0 (measured 2026-07-30:
    2026-only bias +14.2% at T=3 / +4..5% at mid-T while the pooled mean
    read ~0). Fires ONLY when the cohort actually CONTAINS the target year
    (regime_year) with enough records — fitting bias on year-1 and assuming
    carryover measurably overcorrected the 2024 backtest fold. Implements
    what the 04d call site has always claimed ("Recent data is weighted more
    heavily"). The CI width quantile stays pooled: scale is stable across
    years, and n~24 is too thin for an 80th percentile.
    """
    years = [r.year for r in records if r.year is not None]
    if regime_year is not None and years and max(years) == regime_year:
        regime_errs = [r.err_pct for r in records if r.year == regime_year]
        if len(regime_errs) >= regime_min_n:
            return trimmed_mean(regime_errs), f'regime-{regime_year}'
    return trimmed_mean([r.err_pct for r in records]), 'pooled'


def cohort_has_year(records, year):
    """The cohort's most recent records are from `year`."""
    years = [r.year for r in records if r.year is not None]
    return year is not None and bool(years) and max(years) == year


def stationarity_of(records):
    """Mean bias of the older and newer half of the records, or None under 6."""
    if len(records) < 6:
        return None
    err = np.array([r.err_pct for r in records])
    mid = len(records) // 2
    old, new = float(np.mean(err[:mid])), float(np.mean(err[mid:]))
    return {'old_bias_pct': round(old * 100, 1), 'new_bias_pct': round(new * 100, 1),
            'delta_pct': round((new - old) * 100, 1)}


def recent_half_bias(records):
    """(recent records, their IQR-trimmed mean bias) for the carryover refit."""
    recent = records[len(records) // 2:]
    errs = np.array([r.err_pct for r in recent])
    q1, q3 = np.percentile(errs, [25, 75])
    iqr = q3 - q1
    mask = (errs >= q1 - 2 * iqr) & (errs <= q3 + 2 * iqr)
    kept = errs[mask] if mask.sum() >= 3 else errs
    return recent, float(np.mean(kept))


def published_center(r, log_bias_factor, T):
    """The log point the site would publish for the residual's event.

    The bias-corrected model point; inside two weeks, with a pickup, averaged
    with it as forecast.pickup does (shared.pickup_blend), never under the
    count. The published range moves with the point, so its half-width is
    the model's and the scale fits around this center (#191).
    """
    log_model = r.log_point + log_bias_factor
    blended = None if T is None else pickup_blend(math.exp(log_model), r.pickup, T)
    return log_model if blended is None else math.log(max(blended, r.count))


def ci_scale(records, bias_factor, target_coverage, T=None):
    """The width scale that covers target_coverage of the records.

    The empirical quantile of each residual normalized by its half-width,
    around the center the site publishes (published_center); it is already
    in units of half-width, so it is the scale itself (AUDIT.md C1).
    """
    log_bias_factor = np.log(max(bias_factor, 1e-9))
    norm = np.array([abs(r.log_actual - published_center(r, log_bias_factor, T)) / r.log_halfw
                     for r in records])
    return float(np.percentile(norm, target_coverage * 100))
