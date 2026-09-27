"""The live record grades what the site published, on the right day, never a later one."""
import pandas as pd

from perf.live_record import last_run_per_day, match_forecasts, summarize_live

START = pd.Timestamp('2026-06-30')


def _row(as_of, point, run_ts=None, family='World Open, top 6 sections', route='model',
         low=None, high=None, model_hash='aaa'):
    return {'as_of_date': as_of, 'run_ts': run_ts or f'{as_of} 01:00:00', 'origin': 'nightly',
            'published': 1, 'family': family, 'year': 2026, 'point': point,
            'ci_lower': low if low is not None else point - 50,
            'ci_upper': high if high is not None else point + 50,
            'route': route, 'model_hash': model_hash}


def _events(final=1000):
    return pd.DataFrame([{'tid': 7, 'family': 'World Open top 6 sections', 'tournament_year': 2026,
                          'final_count': final, 'start': START}])


def _match(rows, horizons=(14,)):
    return match_forecasts(last_run_per_day(pd.DataFrame(rows)), _events(), horizons)


def test_the_forecast_on_the_day_is_graded_and_the_last_run_wins():
    recs = _match([_row('2026-06-16', 900, '2026-06-16 01:00:00'),
                   _row('2026-06-16', 950, '2026-06-16 13:00:00'),
                   _row('2026-06-15', 800)])
    assert len(recs) == 1
    assert (recs[0]['as_of_date'], recs[0]['point']) == ('2026-06-16', 950.0)
    assert recs[0]['forecast_date'] == '2026-06-16' and recs[0]['in_range'] == 1


def test_a_stand_in_logged_beside_the_forecast_is_not_graded_as_published():
    shadow = {**_row('2026-06-16', 700, '2026-06-16 13:00:00', route='metadata_historical_avg'),
              'published': 0}
    recs = _match([_row('2026-06-16', 950, '2026-06-16 13:00:00'), shadow])
    assert [(r['route'], r['point']) for r in recs] == [('model', 950.0)]


def test_a_missing_day_falls_back_up_to_three_days_never_forward():
    recs = _match([_row('2026-06-13', 900), _row('2026-06-17', 990)])
    assert [(r['as_of_date'], r['point']) for r in recs] == [('2026-06-13', 900.0)]
    assert _match([_row('2026-06-12', 900), _row('2026-06-17', 990)]) == [], \
        "four days early is too stale, and a later row is never used"


def test_the_card_name_joins_its_lineage():
    recs = _match([_row('2026-06-16', 950, family='World Open')])
    assert recs and recs[0]['tid'] == 7


def test_scores_split_by_route_and_version_and_bad_ranges_are_counted():
    rows = [_row('2026-06-16', 950, model_hash='aaa'),
            _row('2026-06-23', 980, route='metadata_pace', model_hash='bbb'),
            _row('2026-06-27', 990, low=995, high=1100, model_hash='bbb')]
    recs = _match(rows, horizons=(14, 7, 3))
    block = summarize_live(recs, '2026-06-16', '2026-06-27')
    assert block['n_records'] == 2 and block['n_invalid_ranges'] == 1
    assert set(block['by_route']) == {'model', 'metadata_pace'}
    assert [e['model_hash'] for e in block['eras']] == ['aaa', 'bbb']
    assert block['pooled']['14']['n'] == 1


def test_no_published_forecast_gives_an_empty_block():
    block = summarize_live([], '2026-06-16', '2026-06-27')
    assert block['n_records'] == 0 and 'pooled' not in block
