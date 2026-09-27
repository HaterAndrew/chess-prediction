"""The corpus as it stood on a date, and counts read only from rows dated by then."""
import numpy as np
import pandas as pd
import pytest

from corpus import Corpus, count_as_of, load_corpus
from corpus.calendar import event_calendar
from corpus.coverage import CARRIED, NOT_OPEN, OBSERVED, UNOBSERVED


def _curve(points):
    return pd.DataFrame({'T': [p[0] for p in points], 'cum_regs': [p[1] for p in points]})


EXPORT = _curve([(60, 30), (30, 80), (7, 150), (0, 200)])


@pytest.mark.parametrize("T, expected", [
    (60, (30, OBSERVED)),
    (45, (30, OBSERVED)),       # no registrations in between: the count stands
    (8, (80, OBSERVED)),        # never the later row at T-7
    (0, (200, OBSERVED)),
    (90, (0, NOT_OPEN)),        # registration had not opened
])
def test_export_counts_carry_forward_until_the_next_registration(T, expected):
    got = count_as_of(EXPORT, T)
    assert (got.count, got.basis) == expected


SCRAPED = _curve([(22, 0), (20, 100), (10, 150), (-2, 300)])


@pytest.mark.parametrize("T, close_T, expected", [
    (20, None, (100, OBSERVED)),
    (18, None, (100, CARRIED)),       # a missed scrape or two
    (17, None, (100, CARRIED)),
    (16, None, (None, UNOBSERVED)),   # more than three days since the last look
    (25, None, (0, NOT_OPEN)),        # a later zero means zero then
    (-6, None, (None, UNOBSERVED)),
    (-6, -2, (300, CARRIED)),         # registration closed: the count is final
])
def test_scraped_counts_carry_three_days_or_past_close(T, close_T, expected):
    got = count_as_of(SCRAPED, T, exact=False, close_T=close_T)
    assert (got.count, got.basis) == expected


def test_a_scraped_curve_with_nothing_before_the_date_is_unobserved():
    got = count_as_of(_curve([(20, 100)]), 25, exact=False)
    assert (got.count, got.basis) == (None, UNOBSERVED)
    assert count_as_of(_curve([]), 10).basis == UNOBSERVED


# A small corpus: Harbor Open 2025 (finished), Harbor Open 2026 (starts
# 2026-05-01), and a 2019 event known only from its summary row.
def _corpus():
    summary = pd.DataFrame({
        'tid': [1, 2, 3],
        'family': ['Harbor Open', 'Harbor Open', 'Old Open'],
        'tournament_year': [2025.0, 2026.0, 2019.0],
        'final_count': [150, 180, 90],
        'last_reg': ['2025-05-03', '2026-05-02', np.nan],
        'first_reg': ['2025-01-10', '2026-04-15', np.nan],
        'has_timestamps': [True, True, False],
    })
    meta = pd.DataFrame({'family': ['Harbor Open', 'Harbor Open'], 'year': [2025, 2026],
                         'start_date': ['2025-05-01', '2026-05-01'],
                         'end_date': ['2025-05-04', '2026-05-03']})
    daily = pd.DataFrame({'tid': [1, 1, 2, 2, 2],
                          'T': [60, 0, 60, 30, 10],
                          'cum_regs': [40, 150, 50, 90, 140],
                          'cum_pct': [0.27, 1.0, 0.28, 0.5, 0.78]})
    standings = pd.DataFrame({'tournament_name': ['Harbor Open', 'Harbor Open', 'Somewhere'],
                              'year': [2025, 2026, 2026], 'total_players': [150, 180, 60]})
    enrichment = pd.DataFrame({'tournament_name': ['2025 Harbor Open', '2026 Harbor Open'],
                               'year': [2025, 2026],
                               'end_date': ['2025-05-04', '2026-05-03']})
    scrape = pd.DataFrame({'date': ['2026-03-01', '2026-04-01', '2026-04-20'],
                           'tournament_name': ['2026 Harbor Open'] * 3,
                           'entry_count': [50, 90, 130]})
    return Corpus(summary, daily, meta, standings, enrichment, scrape)


def test_a_view_hides_what_came_after_its_date():
    view = _corpus().as_of('2026-04-01')
    finals = dict(zip(view.summary['tid'], view.summary['final_count']))
    assert finals[1] == 150 and finals[3] == 90 and np.isnan(finals[2])
    assert view.summary.loc[view.summary['tid'] == 2, 'first_reg'].isna().all()
    assert sorted(view.daily.loc[view.daily['tid'] == 2, 'T']) == [30, 60]
    assert view.daily.loc[view.daily['tid'] == 2, 'cum_pct'].isna().all()
    assert view.daily.loc[view.daily['tid'] == 1, 'cum_pct'].notna().all()
    assert len(view.daily[view.daily['tid'] == 1]) == 2
    assert list(view.standings['year']) == [2025]
    assert list(view.enrichment['year']) == [2025]
    assert list(view.scrape['entry_count']) == [50, 90]
    assert view.meta.equals(_corpus().meta)
    assert view.as_of_date == pd.Timestamp('2026-04-01')


def test_an_event_is_finished_the_day_after_it_ends():
    corpus = _corpus()
    assert np.isnan(corpus.as_of('2026-05-03').summary['final_count'].iloc[1])
    assert corpus.as_of('2026-05-04').summary['final_count'].iloc[1] == 180


def test_this_seasons_standings_appear_once_their_event_is_over():
    assert list(_corpus().as_of('2026-05-04').standings['total_players']) == [150, 180]
    assert list(_corpus().as_of('2027-01-01').standings['total_players']) == [150, 180, 60]


def test_a_view_cannot_see_past_its_own_date():
    view = _corpus().as_of('2026-04-01')
    assert view.as_of('2026-03-01').as_of_date == pd.Timestamp('2026-03-01')
    with pytest.raises(ValueError):
        view.as_of('2026-04-02')


def test_dates_come_from_metadata_then_last_registration_then_year_end():
    cal = event_calendar(_corpus().summary, _corpus().meta).set_index('tid')
    assert cal.loc[2, 'start'] == pd.Timestamp('2026-05-01')
    assert cal.loc[2, 'end'] == pd.Timestamp('2026-05-03')
    assert pd.isna(cal.loc[3, 'start']) and cal.loc[3, 'end'] == pd.Timestamp('2019-12-31')


def _scramble_after(corpus, d):
    """Change everything dated after d, working from the raw frames."""
    meta = corpus.meta.assign(start=pd.to_datetime(corpus.meta['start_date']),
                              end=pd.to_datetime(corpus.meta['end_date']))
    keyed = corpus.summary.merge(
        meta[['family', 'year', 'start', 'end']],
        left_on=['family', 'tournament_year'], right_on=['family', 'year'], how='left')
    summary = corpus.summary.copy()
    unfinished = (keyed['end'] >= d).to_numpy()
    summary.loc[unfinished, 'final_count'] = summary.loc[unfinished, 'final_count'] * 3 + 7
    summary.loc[unfinished, 'last_reg'] = '2099-01-01'
    starts = dict(zip(keyed['tid'], keyed['start']))
    row_date = corpus.daily['tid'].map(starts) - pd.to_timedelta(corpus.daily['T'], unit='D')
    daily = corpus.daily.copy()
    daily.loc[row_date > d, 'cum_regs'] = 99999
    # A share of the final: derived from rows after d.
    pending_tids = set(keyed.loc[unfinished, 'tid'])
    daily.loc[daily['tid'].isin(pending_tids), 'cum_pct'] *= 0.5
    scrape = corpus.scrape.copy()
    scrape.loc[pd.to_datetime(scrape['date']) > d, 'entry_count'] = 99999
    return Corpus(summary, daily, corpus.meta, corpus.standings, corpus.enrichment, scrape)


@pytest.mark.parametrize("d", ['2025-05-01', '2025-05-24', '2026-03-30'])
def test_nothing_after_the_date_reaches_the_view(tmp_output, d):
    d = pd.Timestamp(d)
    corpus = load_corpus(tmp_output)
    scrambled = _scramble_after(corpus, d)
    assert not scrambled.summary.equals(corpus.summary), "the scramble changed something"
    before, after = corpus.as_of(d), scrambled.as_of(d)
    for name in ('summary', 'daily', 'scrape'):
        pd.testing.assert_frame_equal(getattr(before, name), getattr(after, name))
