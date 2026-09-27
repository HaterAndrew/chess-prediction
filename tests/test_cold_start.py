"""A cold-start run forecasts each event as if nothing had trained on its family."""
import pandas as pd
import pytest

import perf.walkforward as wf
from forecast import Event
from perf.cold_start import FINALS, NONE, UNTRAINED, disguise
from perf.wf_run import write_records
from tests.test_walk_forward import _graded_fixture

TODAY = pd.Timestamp('2026-03-21')


def test_a_disguised_event_keeps_its_dates_and_loses_its_name():
    event = Event('Harbor Open', event_start=pd.Timestamp('2026-05-01'),
                  canonical='Harbor Open', names=('Harbor Open', 'Harbour Open'))
    hidden, history, pickup = disguise(event, [90, 100], 104, FINALS)
    assert (hidden.family, hidden.canonical, hidden.names) == (UNTRAINED, UNTRAINED, (UNTRAINED,))
    assert hidden.event_start == event.event_start
    assert (history, pickup) == ([90, 100], None), "its finals are known, its curve is not"
    assert disguise(event, [90, 100], 104, NONE)[1:] == ([], None)
    assert disguise(event, [90, 100], 104, None) == (event, [90, 100], 104)
    with pytest.raises(ValueError):
        disguise(event, [], None, 'warm')


def test_a_cold_start_run_trains_no_family_and_grades_the_same_events(tmp_output):
    corpus = _graded_fixture(tmp_output)
    warm, _ = wf.run_walk_forward(corpus, TODAY)
    cold, _ = wf.run_walk_forward(corpus, TODAY, cold_start=FINALS)
    new, _ = wf.run_walk_forward(corpus, TODAY, cold_start=NONE)
    assert warm and {r['tier'] for r in warm} - {'size-matched'}, "the fixture trains families"
    assert {r['tier'] for r in cold} == {'size-matched'}
    keys = [(r['tid'], r['T'], r['family'], r['final']) for r in warm]
    assert [(r['tid'], r['T'], r['family'], r['final']) for r in cold] == keys
    assert all(r['pickup'] is None for r in cold)
    assert [r['n_history'] for r in cold] == [r['n_history'] for r in warm]
    assert {r['n_history'] for r in new} == {0} and {r['last_year'] for r in new} == {None}


def test_two_cold_start_runs_write_the_same_bytes(tmp_output, tmp_path):
    corpus = _graded_fixture(tmp_output)
    for name in ('a.csv', 'b.csv'):
        write_records(wf.run_walk_forward(corpus, TODAY, cold_start=FINALS)[0], tmp_path / name)
    assert (tmp_path / 'a.csv').read_bytes() == (tmp_path / 'b.csv').read_bytes()
