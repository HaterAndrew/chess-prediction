"""Proper scores, their uncertainty, and the rule a model change must pass."""
import numpy as np
import pandas as pd
import pytest

from perf.acceptance import judge
from perf.log_scores import absolute_log_error, log_interval_score
from perf.stats import block_se, median_ci, wilson

Z90 = 1.2815515655446004  # standard normal 0.9 quantile


def test_log_interval_score_charges_width_and_ten_times_the_miss():
    assert log_interval_score(100, 100, 100) == 0
    inside = log_interval_score(100, 80, 125)
    assert inside == pytest.approx(np.log(125 / 80))
    below = log_interval_score(70, 80, 125)
    assert below == pytest.approx(np.log(125 / 80) + 10 * np.log(80 / 70))
    with pytest.raises(ValueError):
        log_interval_score(100, 120, 110)


def test_absolute_log_error_is_symmetric_in_ratio():
    assert absolute_log_error(100, 110) == pytest.approx(absolute_log_error(110, 100))


def _expected_lis(y, mu, sigma, shift=0.0, scale=1.0):
    lo = np.exp(mu + shift - Z90 * sigma * scale)
    hi = np.exp(mu + shift + Z90 * sigma * scale)
    return log_interval_score(y, np.full_like(y, lo), np.full_like(y, hi)).mean()


def test_the_true_quantiles_score_best_in_expectation():
    rng = np.random.default_rng(1)
    mu, sigma = np.log(200), 0.2
    y = np.exp(rng.normal(mu, sigma, 200_000))
    honest = _expected_lis(y, mu, sigma)
    for shift, scale in [(0, 0.7), (0, 1.4), (0.1, 1.0), (-0.1, 1.0)]:
        assert honest < _expected_lis(y, mu, sigma, shift, scale), (shift, scale)
    median_ale = absolute_log_error(y, np.exp(mu)).mean()
    assert median_ale < absolute_log_error(y, np.exp(mu + 0.05)).mean()
    assert median_ale < absolute_log_error(y, np.exp(mu - 0.05)).mean()


def test_wilson_and_median_intervals():
    assert wilson(8, 10) == (49.0, 94.3)
    assert wilson(0, 0) == (None, None)
    lo, hi = median_ci(np.arange(1, 101))
    assert (lo, hi) == (40.0, 61.0)


def test_block_standard_error_resamples_whole_families():
    values = [1.0, 1.0, 5.0, 5.0]
    assert block_se(values, ['a', 'a', 'b', 'b']) > 0
    assert block_se([2.0, 2.0, 2.0], ['a', 'b', 'c']) == 0
    assert block_se([1.0, 2.0], ['a', 'a']) is None, "one family: no spread to resample"
    assert block_se(values, ['a', 'a', 'b', 'b']) == block_se(values, ['a', 'a', 'b', 'b'])


def _records(width_by_T, shift_by_T=None, seed=0):
    """Four seasons of 30 families at eight horizons; ranges of a set log width."""
    rng = np.random.default_rng(seed)
    shift_by_T = shift_by_T or {}
    rows = []
    for season in (2023, 2024, 2025, 2026):
        for fam in range(30):
            final = int(rng.integers(80, 600))
            for T, width in width_by_T.items():
                noise = rng.normal(0, 0.08)
                point = final * np.exp(noise + shift_by_T.get(T, 0))
                rows.append({'tid': season * 100 + fam, 'T': T, 'season': season,
                             'family': f'F{fam}', 'final': final, 'point': point,
                             'low': point * np.exp(-width), 'high': point * np.exp(width)})
    return rows


WIDE = {T: 0.4 for T in (90, 60, 42, 28, 14, 7, 3, 1)}


def test_judge_accepts_a_planted_gain_in_its_band():
    tighter = {**WIDE, 14: 0.16, 7: 0.16, 3: 0.16, 1: 0.16}
    verdict = judge(_records(tighter), _records(WIDE), band='short')
    assert verdict['accept'], verdict['checks']
    assert verdict['season_wins'] == 4


def test_judge_vetoes_a_regression_at_one_horizon():
    tighter = {**WIDE, 14: 0.16, 7: 0.16, 3: 0.16, 1: 0.16}
    verdict = judge(_records(tighter, shift_by_T={90: 0.3}), _records(WIDE), band='short')
    assert not verdict['accept']
    assert verdict['checks']['no_horizon_worse_by_1se'] is False
    assert verdict['horizons'][90]['lis'] is False


def test_judge_rejects_a_change_that_only_widens():
    verdict = judge(_records({**WIDE, 7: 0.9}), _records(WIDE), band='short')
    assert not verdict['accept']
    assert verdict['checks']['lis_lower_by_1se'] is False


def test_a_removal_that_changes_nothing_is_non_inferior():
    rows = _records(WIDE)
    verdict = judge(rows, rows, kind='removal')
    assert verdict['accept'] and verdict['checks'] == {'no_worse_at_any_horizon': True}


def test_perf_diff_prints_both_files_and_the_verdict(tmp_path, capsys):
    from scripts.perf_diff import main
    for name, rows in (('before', _records(WIDE)), ('after', _records(WIDE))):
        df = pd.DataFrame(rows)
        df['in_range'] = ((df['low'] <= df['final']) & (df['final'] <= df['high'])).astype(int)
        df['log_error'] = np.log(df['point'] / df['final'])
        df.to_csv(tmp_path / f'{name}.csv', index=False)
    code = main([str(tmp_path / 'before.csv'), str(tmp_path / 'after.csv'), '--kind', 'removal'])
    out = capsys.readouterr().out
    assert code == 0 and 'lis_before' in out and '"accept": true' in out
