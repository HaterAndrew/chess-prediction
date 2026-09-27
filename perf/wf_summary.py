"""The walk-forward block of performance_data.json."""
import numpy as np
import pandas as pd

from corpus.coverage import CARRY_DAYS


def _metrics(g):
    pct = (g['point'] - g['final']) / g['final'] * 100
    return {
        'n': int(len(g)),
        'n_events': int(g['tid'].nunique()),
        'mae_pct': round(float(pct.abs().mean()), 2),
        # The typical miss, as a percentage: exp(median log error) - 1.
        'median_error_pct': round(float(np.expm1(g['log_error'].median()) * 100), 2),
        'coverage': round(float(g['in_range'].mean() * 100), 1),
        'below_pct': round(float((g['final'] < g['low']).mean() * 100), 1),
        'above_pct': round(float((g['final'] > g['high']).mean() * 100), 1),
    }


def _by_T(frame):
    return {str(T): _metrics(g) for T, g in frame.groupby('T', sort=False)}


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
