"""The walk-forward backtest makes each forecast as production would have on its date."""
import numpy as np
import pandas as pd
import pytest

import perf.walkforward as wf
from corpus import Corpus, load_corpus
from corpus.coverage import CARRIED, OBSERVED, UNOBSERVED, count_as_of
from forecast import Fitted
from perf.schedule import cutoff_for, forecast_points, monthly_cutoffs
from perf.wf_run import RECORD_COLUMNS, write_records
from perf.wf_summary import summarize
from tests.test_corpus_as_of import _scramble_after

TODAY = pd.Timestamp('2026-09-27')


def test_refits_fall_on_the_first_of_each_month():
    cuts = monthly_cutoffs(2023, '2023-03-15')
    assert cuts == [pd.Timestamp('2023-01-01'), pd.Timestamp('2023-02-01'),
                    pd.Timestamp('2023-03-01')]
    assert cutoff_for('2023-02-28', cuts) == pd.Timestamp('2023-02-01')
    assert cutoff_for('2023-03-01', cuts) == pd.Timestamp('2023-03-01')
    assert cutoff_for('2022-12-31', cuts) is None


def test_forecasts_are_dated_start_minus_T_and_never_after_today():
    events = pd.DataFrame({'tid': [7], 'start': [pd.Timestamp('2023-03-10')]})
    cuts = monthly_cutoffs(2023, '2023-03-08')
    points = forecast_points(events, [90, 28, 7, 1], cuts, '2023-03-08')
    assert points == [(7, 28, pd.Timestamp('2023-02-10'), pd.Timestamp('2023-02-01')),
                      (7, 7, pd.Timestamp('2023-03-03'), pd.Timestamp('2023-03-01'))]


@pytest.mark.parametrize("T, expected", [
    (40, (80, OBSERVED)),     # before the snapshot the export is exact
    (29, (80, CARRIED)),      # the snapshot at T-30 stands as an observation
    (26, (None, UNOBSERVED)),  # four days past it, nothing new was seen
    (10, (150, OBSERVED)),    # a scraped row after the snapshot
])
def test_an_export_is_exact_only_through_its_snapshot(T, expected):
    curve = pd.DataFrame({'T': [60, 45, 10], 'cum_regs': [30, 80, 150]})
    got = count_as_of(curve, T, exact_until_T=30)
    assert (got.count, got.basis) == expected


class _Model:
    _last_tier = 'family-direct'

    def predict_nowcast(self, count, T, family, **kw):
        return count * 2, round(count * 1.5), count * 3


def _new_year_corpus():
    summary = pd.DataFrame({
        'tid': [1, 2], 'tournament_name': ['2026 Harbor Open', '2027 Harbor Open'],
        'family': ['Harbor Open'] * 2, 'tournament_year': [2026.0, 2027.0],
        'final_count': [200, 220], 'last_reg': ['2026-01-24', '2027-01-23'],
        'has_timestamps': [True, True], 'is_online': [False, False], 'is_covid': [False, False],
    })
    meta = pd.DataFrame({'family': ['Harbor Open'] * 2, 'year': [2026, 2027],
                         'start_date': ['2026-01-22', '2027-01-21'],
                         'end_date': ['2026-01-24', '2027-01-23']})
    daily = pd.DataFrame({'tid': [1] * 3 + [2] * 3, 'T': [30, 14, 0] * 2,
                          'cum_regs': [60, 120, 190, 70, 130, 210]})
    # Scraped daily through the close, so its final is labelled final.
    days = pd.date_range('2027-01-09', '2027-01-23').strftime('%Y-%m-%d')
    scrape = pd.DataFrame({'date': days, 'tournament_name': '2027 Harbor Open',
                           'entry_count': 210})
    return Corpus(summary, daily, meta, None, pd.DataFrame(), scrape)


def test_a_january_forecast_is_fitted_for_the_new_season(monkeypatch):
    seasons = []

    def fake_fit(view, season):
        seasons.append((view.as_of_date, season, wf.completed_in(view, season)))
        return Fitted(model=_Model()), []
    monkeypatch.setattr(wf, 'fit_as_of', fake_fit)
    records, _ = wf.run_walk_forward(_new_year_corpus(), '2027-02-10',
                                     first_season=2027, horizons=[14])
    assert seasons == [(pd.Timestamp('2027-01-01'), 2027, set())]
    assert [(r['tid'], r['forecast_date'], r['count']) for r in records] == [(2, '2027-01-07', 130)]
    # The model's 260 averaged in log space with pickup, 130 + (200 - 120).
    assert (records[0]['pickup'], records[0]['raw_point'], records[0]['point']) == (210, 260, 234)
    assert records[0]['in_range'] == 1


def _graded_fixture(output_dir):
    """The fixture corpus with finals in line with its curves.

    The fixture's curves peak near a quarter of its finals, so the frozen-curve
    gate would grade nothing; a final 5% above the curve's peak passes it.
    """
    corpus = load_corpus(output_dir)
    peaks = corpus.daily.groupby('tid')['cum_regs'].max()
    summary = corpus.summary.copy()
    has_curve = summary['tid'].isin(peaks.index)
    summary.loc[has_curve, 'final_count'] = (
        summary.loc[has_curve, 'tid'].map(peaks) * 1.05).round().astype(int)
    return Corpus(summary, corpus.daily, corpus.meta, corpus.standings,
                  corpus.enrichment, corpus.scrape)


def test_nothing_after_the_forecast_date_moves_the_forecast(tmp_output):
    corpus = _graded_fixture(tmp_output)
    d = pd.Timestamp('2025-04-24')          # Chicago Open 2025 at T-28
    before, _ = wf.run_walk_forward(corpus, TODAY)
    # Finals only nudged: which events are graded depends on their finals,
    # which is known today; what each forecast said must not.
    after, _ = wf.run_walk_forward(_scramble_after(corpus, d, final_scale=1.05), TODAY)

    def made_by(records):
        return {(r['tid'], r['T']): (r['count'], r['point'], r['low'], r['high'])
                for r in records if pd.Timestamp(r['forecast_date']) <= d}
    early, late = made_by(before), made_by(after)
    assert (2021, 28) in early and (2021, 28) in late
    assert early == late


def test_records_and_summary_keep_their_shape(tmp_path):
    rec = {'season': 2025, 'tid': 1, 'family': 'Harbor Open', 'T': 7,
           'forecast_date': '2025-04-24', 'cutoff': '2025-04-01', 'count': 90,
           'count_basis': OBSERVED, 'point': 110, 'low': 95, 'high': 130, 'raw_point': 110,
           'final': 100, 'log_error': round(float(np.log(1.1)), 6), 'in_range': 1,
           'route': 'model', 'tier': 'family-direct', 'last_year': 95, 'pickup': 104}
    path = tmp_path / 'records.csv'
    write_records([rec], path)
    assert list(pd.read_csv(path).columns) == RECORD_COLUMNS
    write_records([], path)
    assert list(pd.read_csv(path).columns) == RECORD_COLUMNS
    block = summarize([rec], 2023, 45, pd.Timestamp('2026-03-21'))
    got = block['pooled']['7']
    assert {k: got[k] for k in ('n', 'n_events', 'mae_pct', 'median_error_pct', 'coverage',
                                'below_pct', 'above_pct')} == {
        'n': 1, 'n_events': 1, 'mae_pct': 10.0, 'median_error_pct': 10.0,
        'coverage': 100.0, 'below_pct': 0.0, 'above_pct': 0.0}
    assert got['ale'] == {'mean': round(float(np.log(1.1)), 4), 'se': None}
    assert block['by_season']['2025']['7']['n'] == 1
    assert summarize([], 2023, 45, pd.Timestamp('2026-03-21'))['n_records'] == 0
