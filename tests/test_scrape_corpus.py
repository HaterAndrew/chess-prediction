"""Curves and final labels built from the nightly scrape."""
import os

import pandas as pd

from corpus import load_corpus
from corpus.coverage import count_as_of
from corpus.labels import FINAL, OPEN, PROVISIONAL, final_labels, scrape_dates, watched_to_close
from corpus.scrape_curves import scrape_curves
from shared.curves import has_curve

START = pd.Timestamp('2026-07-17')


def _scrape(name, counts, first='2026-07-10'):
    days = pd.date_range(first, periods=len(counts), freq='D')
    return pd.DataFrame({'date': days.strftime('%Y-%m-%d'), 'tournament_name': name,
                         'entry_count': counts})


def _summary(final=150):
    return pd.DataFrame({'tid': [1, 2], 'tournament_name': ['2026 Scraped Open', '2026 Export Open'],
                         'final_count': [final, 300]})


CAL = pd.DataFrame({'tid': [1, 2], 'start': [START, START]})


def test_a_scraped_edition_gets_a_gross_running_max_curve_before_its_start():
    # Jul 10..19: a dip on Jul 13 (a correction) and rows on and after the start.
    scrape = _scrape('2026 Scraped Open', [0, 40, 60, 55, 90, 110, 130, 150, 150, 150])
    curves = scrape_curves(scrape, _summary(), CAL, have_curve={2})
    assert curves['tid'].unique().tolist() == [1]
    assert curves['T'].tolist() == [6, 5, 4, 3, 2, 1, 0], "no zero day, nothing after the start"
    assert curves['cum_regs'].tolist() == [40, 60, 60, 90, 110, 130, 150]
    assert curves['daily_regs'].sum() == 150 and curves['cum_pct'].iloc[-1] == 1.0


def test_a_still_registering_edition_ends_at_its_latest_count():
    # Jul 10..14, all before the Jul 17 start: 55 entries, five deleted, then four more.
    scrape = _scrape('2026 Scraped Open', [54, 55, 50, 52, 54])
    curves = scrape_curves(scrape, _summary(), CAL, have_curve={2})
    assert curves['cum_regs'].tolist() == [50, 50, 50, 52, 54], \
        "the least count from each day on: never above the live count, never falling"
    # The scrape ran on to Jul 20 but lost this edition before its Jul 17 start: it has started.
    later = pd.concat([scrape, _scrape('2026 Other Open', [9], first='2026-07-20')])
    assert scrape_curves(later, _summary(), CAL, have_curve={2})['cum_regs'].tolist() == \
        [54, 55, 55, 55, 55], "a started edition keeps the running maximum"


def test_an_edition_with_a_curve_is_left_alone():
    scrape = _scrape('2026 Export Open', [10, 20])
    assert scrape_curves(scrape, _summary(), CAL, have_curve={2}).empty
    assert scrape_curves(None, _summary(), CAL, have_curve=set()).empty


def test_a_scraped_curve_is_an_observation_not_a_full_record():
    curves = scrape_curves(_scrape('2026 Scraped Open', [40, 60]), _summary(), CAL, have_curve=set())
    before = count_as_of(curves, 30, exact=False)
    assert before.count is None, "entries before the first scrape are unknown, not zero"
    assert count_as_of(curves, 7, exact=False).count == 40


def test_has_curve_falls_back_to_the_export_flag():
    loaded = pd.DataFrame({'has_timestamps': [True, False], 'has_curve': [True, True]})
    written = pd.DataFrame({'has_timestamps': [True, False]})
    assert has_curve(loaded).tolist() == [True, True]
    assert has_curve(written).tolist() == [True, False]


def _days(*iso):
    return [pd.Timestamp(d) for d in iso]


def test_the_scrape_must_follow_registration_to_its_close():
    end = pd.Timestamp('2026-07-19')
    daily = list(pd.date_range('2026-07-01', '2026-07-20'))
    assert watched_to_close(daily, end)
    assert not watched_to_close(daily[:-2], end), "stopped before the last day"
    gap = [d for d in daily if not pd.Timestamp('2026-07-10') <= d <= pd.Timestamp('2026-07-14')]
    assert not watched_to_close(gap, end), "missed five days in the last two weeks"
    short_gap = [d for d in daily if d != pd.Timestamp('2026-07-12')]
    assert watched_to_close(short_gap, end)
    assert not watched_to_close(_days('2026-07-18', '2026-07-19'), end), "joined too late"
    assert watched_to_close(list(pd.date_range('2026-07-06', '2026-07-19')), end), \
        "joined a day into the window: within the carry"


def test_labels_final_provisional_and_open():
    ev = pd.DataFrame({'end': pd.to_datetime(['2026-03-01', '2026-06-01', '2026-06-01', '2026-10-01']),
                       'tournament_name': ['A', 'B', 'C', 'D']})
    scrape = pd.concat([_scrape('B', [5] * 30, first='2026-05-10'), _scrape('C', [5] * 3, first='2026-05-30')])
    labels = final_labels(ev, pd.Timestamp('2026-09-27'), pd.Timestamp('2026-03-21'), scrape_dates(scrape))
    assert labels.tolist() == [FINAL, FINAL, PROVISIONAL, OPEN]


def test_the_scrape_joins_an_export_name_that_lost_its_comma():
    ev = pd.DataFrame({'end': [pd.Timestamp('2026-06-01')],
                       'tournament_name': ['2026 World Open  top 6 sections']})
    scrape = _scrape('2026 World Open, top 6 sections', [5] * 30, first='2026-05-10')
    labels = final_labels(ev, pd.Timestamp('2026-09-27'), pd.Timestamp('2026-03-21'), scrape_dates(scrape))
    assert labels.tolist() == [FINAL]


def test_the_loader_gives_a_scraped_edition_its_curve(tmp_output):
    summary = pd.read_csv(os.path.join(tmp_output, 'tournament_summary.csv'))
    meta = pd.read_csv(os.path.join(tmp_output, 'tournament_metadata.csv'))
    tid = int(summary['tid'].max()) + 1
    row = {**summary.iloc[0].to_dict(), 'tid': tid, 'tournament_name': '2026 Scraped Open',
           'family': 'Scraped Open', 'tournament_year': 2026, 'final_count': 150,
           'has_timestamps': False}
    pd.concat([summary, pd.DataFrame([row])]).to_csv(os.path.join(tmp_output, 'tournament_summary.csv'),
                                                    index=False)
    meta_row = {**meta.iloc[0].to_dict(), 'family': 'Scraped Open', 'year': 2026,
                'start_date': '2026-07-17', 'end_date': '2026-07-19'}
    pd.concat([meta, pd.DataFrame([meta_row])]).to_csv(os.path.join(tmp_output, 'tournament_metadata.csv'),
                                                      index=False)
    _scrape('2026 Scraped Open', [40, 60, 90]).to_csv(os.path.join(tmp_output, 'daily_scrape.csv'),
                                                      index=False)
    corpus = load_corpus(tmp_output)
    curve = corpus.daily[corpus.daily['tid'] == tid]
    assert curve['T'].tolist() == [7, 6, 5] and curve['cum_regs'].tolist() == [40, 60, 90]
    flags = corpus.summary.set_index('tid')['has_curve']
    assert bool(flags[tid]) and flags.sum() == summary['has_timestamps'].sum() + 1


def test_a_relocated_edition_finds_its_dates_under_its_canonical_name():
    from corpus.calendar import event_calendar
    summary = pd.DataFrame({'tid': [1, 2], 'family': ['Eastern Chess Congress', 'Eastern Open'],
                            'tournament_year': [2026, 2026], 'last_reg': [None, None]})
    meta = pd.DataFrame({'family': ['Eastern Chess Congress (in New Jersey)', 'Eastern Open'],
                         'year': [2026, 2026], 'start_date': ['2026-10-23', '2026-12-26'],
                         'end_date': ['2026-10-25', '2026-12-29']})
    cal = event_calendar(summary, meta).set_index('tid')
    assert cal.loc[1, 'start'] == pd.Timestamp('2026-10-23')
    assert cal.loc[2, 'start'] == pd.Timestamp('2026-12-26'), "an exact match stays exact"
