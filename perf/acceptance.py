"""judge(): does a model change beat the incumbent on the walk-forward?

Both record sets are paired on (event, horizon). An improvement must, in its
target band, lower the mean log interval score by more than one standard
error, raise the mean absolute log error by no more than half of one, be no
worse than one standard error at any horizon, and win in at least three of
four seasons. A removal must be no worse than one standard error at every
horizon on both scores. Standard errors resample whole families.

A change that touches only a named subset of forecasts cannot win seasons it
has no forecasts in, so it is judged inside the subset (kind='subset'): both
scores lower by more than one standard error there, at least three seasons
with forecasts in it and all but one of them won, and every forecast outside
it left as it was. kind='no_worse' asks only that neither score is higher by
more than one standard error, in the subset or over all forecasts.
"""
import numpy as np
import pandas as pd

from perf.log_scores import absolute_log_error, log_interval_score
from perf.stats import block_se

BANDS = {'long': (90, 60, 42, 28), 'short': (14, 7, 3, 1)}
MIN_SEASON_WINS = 3
# A subset needs forecasts in this many seasons before it can be judged.
MIN_SUBSET_SEASONS = 3

# Named subsets of the paired forecasts, by the incumbent's record.
SUBSETS = {
    'thin_history': lambda p: p['n_history'] <= 1,
    'few_editions': lambda p: p['n_history'].between(2, 3),
}
# Incumbent columns the subsets read, carried into the pairing when present.
CARRIED = ('n_history',)


def paired(challenger, incumbent):
    """One row per (event, horizon) both made, with the challenger-minus-incumbent scores."""
    cols = ['tid', 'T', 'season', 'family', 'final', 'point', 'low', 'high']
    c = pd.DataFrame(challenger)[cols]
    i = pd.DataFrame(incumbent)
    i = i[cols + [col for col in CARRIED if col in i.columns]]
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


def _lower_by_1se(frame, col):
    mean, se = _mean_se(frame, col)
    return se is not None and mean < -se


def _figures(frame):
    lis, lis_se = _mean_se(frame, 'd_lis')
    ale, ale_se = _mean_se(frame, 'd_ale')
    return {'n': len(frame), 'd_lis': round(lis, 4), 'd_lis_se': _round(lis_se),
            'd_ale': round(ale, 4), 'd_ale_se': _round(ale_se)}


def _inside(p, subset):
    return p if subset is None else p[SUBSETS[subset](p)]


def _unchanged(p):
    return bool((p[['point_c', 'low_c', 'high_c']].to_numpy()
                 == p[['point_i', 'low_i', 'high_i']].to_numpy()).all())


def _judge_removal(p, band, subset):
    horizons = _horizons(p)
    checks = {'no_worse_at_any_horizon': all(h['lis'] and h['ale'] for h in horizons.values())}
    return {'n': len(p), 'checks': checks, 'horizons': horizons}


def _judge_improvement(p, band, subset):
    horizons = _horizons(p)
    in_band = p[p['T'].isin(BANDS[band])]
    ale, ale_se = _mean_se(in_band, 'd_ale')
    wins = int((in_band.groupby('season')['d_lis'].mean() < 0).sum())
    checks = {
        'lis_lower_by_1se': _lower_by_1se(in_band, 'd_lis'),
        'ale_up_at_most_half_se': ale_se is not None and ale <= 0.5 * ale_se,
        'no_horizon_worse_by_1se': all(h['lis'] for h in horizons.values()),
        'wins_3_of_4_seasons': wins >= MIN_SEASON_WINS,
    }
    return {'band': band, **_figures(in_band), 'season_wins': wins, 'checks': checks,
            'horizons': horizons}


def _judge_subset(p, band, subset):
    inside = SUBSETS[subset](p)
    within = p[inside]
    by_season = within.groupby('season')['d_lis'].mean()
    wins = int((by_season < 0).sum())
    checks = {
        'outside_unchanged': _unchanged(p[~inside]),
        'lis_lower_by_1se': _lower_by_1se(within, 'd_lis'),
        'ale_lower_by_1se': _lower_by_1se(within, 'd_ale'),
        'seasons_in_subset': len(by_season) >= MIN_SUBSET_SEASONS,
        'wins_all_but_one_season': wins >= len(by_season) - 1,
    }
    return {'subset': subset, **_figures(within), 'seasons': len(by_season),
            'season_wins': wins, 'checks': checks}


def _judge_no_worse(p, band, subset):
    within = _inside(p, subset)
    checks = {'lis_no_worse_by_1se': _not_worse(within, 'd_lis'),
              'ale_no_worse_by_1se': _not_worse(within, 'd_ale')}
    return {'subset': subset, **_figures(within), 'checks': checks}


KINDS = {'improvement': _judge_improvement, 'removal': _judge_removal,
         'subset': _judge_subset, 'no_worse': _judge_no_worse}


def judge(challenger, incumbent, band=None, kind='improvement', subset=None):
    """The verdict and each check behind it."""
    verdict = KINDS[kind](paired(challenger, incumbent), band, subset)
    return {'accept': all(verdict['checks'].values()), 'kind': kind, **verdict}


def _horizons(p):
    return {int(T): {'lis': _not_worse(g, 'd_lis'), 'ale': _not_worse(g, 'd_ale')}
            for T, g in p.groupby('T')}


def _round(v):
    return None if v is None or np.isnan(v) else round(v, 4)
