"""The walk-forward block of performance_data.json.

Per horizon: the error and coverage figures the page has always shown, the
proper scores (absolute log error, log interval score) with family-block
standard errors, the coverage and median error with their intervals, and
the model against the last-year and pickup baselines on the same forecasts.
"""
import numpy as np
import pandas as pd

from corpus.coverage import CARRY_DAYS
from perf.log_scores import absolute_log_error, log_interval_score
from perf.stats import block_se, median_ci, wilson

BASELINES = ('last_year', 'pickup')


def _pct(log_value):
    return None if log_value is None else round(float(np.expm1(log_value) * 100), 2)


def _mean_se(values, families):
    se = block_se(values, families)
    return {'mean': round(float(np.mean(values)), 4),
            'se': None if se is None else round(se, 4)}


def _versus(g, col):
    """Model and baseline absolute log error on the forecasts where the baseline exists."""
    b = g[g[col].notna()]
    if b.empty:
        return {'n': 0}
    model = absolute_log_error(b['final'], b['point'])
    base = absolute_log_error(b['final'], b[col])
    diff = _mean_se(model - base, b['family'])
    return {'n': int(len(b)), 'ale': round(float(base.mean()), 4),
            'model_ale': round(float(model.mean()), 4),
            'diff': diff['mean'], 'diff_se': diff['se']}


def horizon_metrics(g):
    """The walk-forward figures for one horizon's records."""
    pct = (g['point'] - g['final']) / g['final'] * 100
    med_lo, med_hi = median_ci(g['log_error'])
    return {
        'n': int(len(g)),
        'n_events': int(g['tid'].nunique()),
        'mae_pct': round(float(pct.abs().mean()), 2),
        # The typical miss, as a percentage: exp(median log error) - 1.
        'median_error_pct': round(float(np.expm1(g['log_error'].median()) * 100), 2),
        'median_error_ci': [_pct(med_lo), _pct(med_hi)],
        'coverage': round(float(g['in_range'].mean() * 100), 1),
        'coverage_ci': list(wilson(int(g['in_range'].sum()), len(g))),
        'below_pct': round(float((g['final'] < g['low']).mean() * 100), 1),
        'above_pct': round(float((g['final'] > g['high']).mean() * 100), 1),
        'ale': _mean_se(absolute_log_error(g['final'], g['point']), g['family']),
        'lis': _mean_se(log_interval_score(g['final'], g['low'], g['high']), g['family']),
        'baselines': {col: _versus(g, col) for col in BASELINES if col in g.columns},
    }


def _by_T(frame):
    return {str(T): horizon_metrics(g) for T, g in frame.groupby('T', sort=False)}


def summarize(records, first_season, n_cutoffs, snapshot):
    """Pooled and per-season metrics by horizon, with the protocol that made them."""
    protocol = {
        'first_season': int(first_season),
        'refit': 'monthly',
        'cutoffs': int(n_cutoffs),
        'count_rule': (f"rows dated by the forecast date; the export is exact through "
                       f"its snapshot ({snapshot.strftime('%Y-%m-%d')}), later counts "
                       f"carry at most {CARRY_DAYS} days"),
    }
    if not records:
        return {'protocol': protocol, 'n_records': 0}
    df = pd.DataFrame(records).sort_values(['T', 'forecast_date', 'tid'],
                                           ascending=[False, True, True])
    return {
        'protocol': protocol,
        'n_records': int(len(df)),
        'n_events': int(df['tid'].nunique()),
        'pooled': _by_T(df),
        'by_season': {str(season): _by_T(g) for season, g in df.groupby('season')},
    }
