"""The residuals recalibrate() fits on: each finished event's forecast at T against its final.

One Residual per cohort event and horizon: the nowcast's forecast for the
count the event had T days out, made without recalibration and, under loo,
without the event's own ratio (v5 Cat L), set against the final it drew.
With the event's pickup gain (forecast.cohort_pickup) it also carries the
pickup the published forecast would have blended in.
"""
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Residual:
    err_pct: float
    log_actual: float
    log_point: float
    # Half-width of the interval production would publish, in log space.
    log_halfw: float
    # The pre-recalibration interval held the final.
    ci_hit: int
    last_reg: Any
    in_sample: bool
    year: Optional[int]
    count: int = 0
    # The event's count plus its last edition's gain after T, when known.
    pickup: Optional[int] = None


def count_near(daily, tid, T):
    """The event's count at the row nearest T within two days, or None."""
    td = daily[daily['tid'] == tid].sort_values('T', ascending=False)
    if len(td) == 0:
        return None
    available = td[(td['T'] >= T - 2) & (td['T'] <= T + 2)].copy()
    if len(available) == 0:
        return None
    available['dist'] = (available['T'] - T).abs()
    count = int(available.sort_values('dist').iloc[0]['cum_regs'])
    return count if count > 0 else None


def raw_forecast(model, count, T, family, tid, loo):
    """(point, low, high, width_low, width_high) without recalibration.

    Under loo the point leaves the tournament's own ratio out (v5 Cat L) and
    the width bounds are the full-list interval's.
    """
    # The blank-and-restore must survive an exception from either
    # predict_nowcast call (2026-09-07 review). Without the finally,
    # one raising tournament left _recal_bias = {} on the instance
    # for good: recalibration silently switched off for every
    # remaining T and for every production prediction that model
    # went on to make, with nothing logged.
    old_bias = model._recal_bias
    old_ci = model._recal_ci
    try:
        model._recal_bias = {}
        model._recal_ci = {}
        point, lo, hi = model.predict_nowcast(
            count, T, family, _track_tier=False,
            _exclude_tid=tid if loo else None)
        # v5 Cat L width geometry: the LOO interval is systematically
        # WIDER than the interval production will publish — dropping a
        # ratio from a 3-5 entry family list triggers the small-n EB
        # sigma floor. Normalizing honest residuals by LOO widths
        # understated the needed scale (measured: fold ci_adj fell to
        # the 0.5 floor and fold coverage collapsed to ~41%). So: LOO
        # point for the residual NUMERATOR (honest location error),
        # full-list width for the DENOMINATOR (application geometry).
        lo_w, hi_w = lo, hi
        if loo:
            point_full, lo_full, hi_full = model.predict_nowcast(
                count, T, family, _track_tier=False)
            if (point_full is not None and point_full > 0
                    and lo_full > 0 and hi_full > 0):
                lo_w, hi_w = lo_full, hi_full
    finally:
        model._recal_bias = old_bias
        model._recal_ci = old_ci
    return point, lo, hi, lo_w, hi_w


def residual(model, row, daily, T, loo, gains=None):
    """The cohort event's Residual at T, or None when it has no usable forecast.

    gains: {(tid, T): pickup gain}; None or a missing key means no pickup.
    """
    tid, family, actual = row['tid'], row['family'], row['final_count']
    count = count_near(daily, tid, T)
    if count is None:
        return None
    gain = (gains or {}).get((tid, T))
    point, lo, hi, lo_w, hi_w = raw_forecast(model, count, T, family, tid, loo)
    if point is None or point <= 0 or lo <= 0 or hi <= 0:
        return None
    # Half-width in log space (the lognormal CI's natural unit)
    log_halfw = (np.log(max(hi_w, 1)) - np.log(max(lo_w, 1))) / 2.0
    if log_halfw <= 0:
        return None
    year = row.get('tournament_year')
    return Residual(
        err_pct=(point - actual) / actual,
        log_actual=np.log(max(actual, 1)),
        log_point=np.log(max(point, 1)),
        log_halfw=log_halfw,
        # coverage_before describes the interval production would
        # publish (pre-recal), so it uses the application-width bounds.
        ci_hit=1 if lo_w <= actual <= hi_w else 0,
        last_reg=row.get('_lr', pd.NaT) if '_lr' in row else pd.NaT,
        in_sample=tid in getattr(model, '_fit_tids', set()),
        year=int(year) if pd.notna(year) else None,
        count=count, pickup=None if gain is None else count + gain)


def residuals_at(model, cohort, daily, T, loo, gains=None):
    """Every cohort event's Residual at T, in the cohort's order."""
    out = []
    for _, row in cohort.iterrows():
        r = residual(model, row, daily, T, loo, gains)
        if r is not None:
            out.append(r)
    return out
