"""Which route should speak for an event: the model, its live pace, or the history?

Every walk-forward forecast is also made by the routes that stand in for the
model off the roster (forecast.shadow_forecasts). Here each stand-in is scored
against the model on the same forecasts, bucketed by horizon band, the count
on the day and how many past finals the family has. A stand-in earns a bucket
only when its log interval score beats the model's by more than one
family-block standard error on at least MIN_N forecasts; otherwise the model
keeps it, the rule the site routes by.
"""
import pandas as pd

from forecast.routes import HISTORICAL_AVG, PACE
from perf.acceptance import BANDS
from perf.log_scores import absolute_log_error, log_interval_score
from perf.stats import block_se

COUNT_BANDS = ((1, 9, '1-9'), (10, 29, '10-29'), (30, 99, '30-99'), (100, None, '100+'))
HISTORY_BANDS = ((0, 0, '0'), (1, 2, '1-2'), (3, None, '3+'))
STAND_INS = {PACE: 'pace', HISTORICAL_AVG: 'hist'}
MIN_N = 20
MODEL, STAND_IN, TOO_FEW = 'model', 'stand-in', 'too few'


def band_of(value, bands):
    """The label of the band holding value."""
    return next(label for lo, hi, label in bands if value >= lo and (hi is None or value <= hi))


def _horizon_band(T):
    return next(name for name, horizons in BANDS.items() if T in horizons)


def bucketed(records):
    """The records with their horizon, count and history bands."""
    df = pd.DataFrame(records)
    return df.assign(band=df['T'].map(_horizon_band),
                     count_band=df['count'].map(lambda c: band_of(c, COUNT_BANDS)),
                     history=df['n_history'].map(lambda n: band_of(n, HISTORY_BANDS)))


def _mean_se(values, families):
    se = block_se(values, families)
    return round(float(values.mean()), 4), None if se is None else round(se, 4)


def compare(g, prefix):
    """The model against one stand-in on the forecasts both made."""
    g = g[g[f'{prefix}_point'].notna()]
    if g.empty:
        return None
    lis_m = log_interval_score(g['final'], g['low'], g['high'])
    lis_s = log_interval_score(g['final'], g[f'{prefix}_low'], g[f'{prefix}_high'])
    diff, se = _mean_se(lis_m - lis_s, g['family'])
    verdict = (TOO_FEW if len(g) < MIN_N or se is None
               else STAND_IN if diff - se > 0 else MODEL)
    return {'n': int(len(g)), 'n_families': int(g['family'].nunique()),
            'model_lis': round(float(lis_m.mean()), 4), 'stand_in_lis': round(float(lis_s.mean()), 4),
            'lis_diff': diff, 'lis_diff_se': se,
            'model_ale': round(float(absolute_log_error(g['final'], g['point']).mean()), 4),
            'stand_in_ale': round(float(absolute_log_error(g['final'], g[f'{prefix}_point']).mean()), 4),
            'verdict': verdict}


def route_evidence(records):
    """One row per bucket and stand-in: the scores, their difference and the verdict."""
    if not records:
        return []
    rows = []
    for (band, count_band, history), g in bucketed(records).groupby(['band', 'count_band', 'history']):
        for route, prefix in STAND_INS.items():
            c = compare(g, prefix)
            if c is not None:
                rows.append({'band': band, 'count_band': count_band, 'history': history,
                             'route': route, **c})
    return rows
