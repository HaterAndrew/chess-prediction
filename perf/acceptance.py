"""judge(): does a model change beat the incumbent on the walk-forward?

Both record sets are paired on (event, horizon). An improvement must, in its
target band, lower the mean log interval score by more than one standard
error, raise the mean absolute log error by no more than half of one, be no
worse than one standard error at any horizon, and win in at least three of
four seasons. A removal must be no worse than one standard error at every
horizon on both scores. Standard errors resample whole families.
"""
import numpy as np
import pandas as pd

from perf.log_scores import absolute_log_error, log_interval_score
from perf.stats import block_se

BANDS = {'long': (90, 60, 42, 28), 'short': (14, 7, 3, 1)}
MIN_SEASON_WINS = 3


def paired(challenger, incumbent):
    """One row per (event, horizon) both made, with the challenger-minus-incumbent scores."""
    cols = ['tid', 'T', 'season', 'family', 'final', 'point', 'low', 'high']
    c = pd.DataFrame(challenger)[cols]
    i = pd.DataFrame(incumbent)[cols]
    p = c.merge(i, on=['tid', 'T', 'season', 'family', 'final'], suffixes=('_c', '_i'))
    p['d_lis'] = (log_interval_score(p['final'], p['low_c'], p['high_c'])
                  - log_interval_score(p['final'], p['low_i'], p['high_i']))
    p['d_ale'] = (absolute_log_error(p['final'], p['point_c'])
                  - absolute_log_error(p['final'], p['point_i']))
    return p


def _mean_se(frame, col):
    return float(frame[col].mean()), block_se(frame[col], frame['family'])


def _not_worse(frame, col):
    mean, se = _mean_se(frame, col)
    return se is not None and mean <= se


def judge(challenger, incumbent, band=None, kind='improvement'):
    """The verdict and each check behind it."""
    p = paired(challenger, incumbent)
    horizons = {int(T): {'lis': _not_worse(g, 'd_lis'), 'ale': _not_worse(g, 'd_ale')}
                for T, g in p.groupby('T')}
    if kind == 'removal':
        checks = {'no_worse_at_any_horizon': all(h['lis'] and h['ale'] for h in horizons.values())}
        return {'accept': all(checks.values()), 'kind': kind, 'n': len(p),
                'checks': checks, 'horizons': horizons}
    in_band = p[p['T'].isin(BANDS[band])]
    lis, lis_se = _mean_se(in_band, 'd_lis')
    ale, ale_se = _mean_se(in_band, 'd_ale')
    wins = int((in_band.groupby('season')['d_lis'].mean() < 0).sum())
    checks = {
        'lis_lower_by_1se': lis_se is not None and lis < -lis_se,
        'ale_up_at_most_half_se': ale_se is not None and ale <= 0.5 * ale_se,
        'no_horizon_worse_by_1se': all(h['lis'] for h in horizons.values()),
        'wins_3_of_4_seasons': wins >= MIN_SEASON_WINS,
    }
    return {'accept': all(checks.values()), 'kind': kind, 'band': band, 'n': len(in_band),
            'd_lis': round(lis, 4), 'd_lis_se': _round(lis_se),
            'd_ale': round(ale, 4), 'd_ale_se': _round(ale_se),
            'season_wins': wins, 'checks': checks, 'horizons': horizons}


def _round(v):
    return None if v is None or np.isnan(v) else round(v, 4)
