"""An event with no past final moves toward what first editions draw, far out only."""
import math

import numpy as np
import pandas as pd
import pytest

from forecast import Event, Fitted, Forecast, Observation, forecast_event
from forecast.new_event import (MIN_FIRST_EDITIONS, NEW_SINCE, blend_new_event_prior,
                                new_event_prior, prior_weight)
from forecast.routes import MODEL

PRIOR = (10.0, 100.0, 400.0)


class _Model:
    _last_tier = 'size-matched'

    def __init__(self, answer):
        self.answer = answer

    def predict_nowcast(self, count, T, family, **kw):
        return self.answer


def _first_editions(finals, first_year=NEW_SINCE):
    """One family per final, first seen in first_year, with a bigger second edition after it."""
    rows = []
    for i, final in enumerate(finals):
        rows += [{'family': f'F{i}', 'tournament_year': first_year, 'final_count': final},
                 {'family': f'F{i}', 'tournament_year': first_year + 1, 'final_count': 10 * final}]
    return pd.DataFrame(rows)


def test_the_prior_reads_each_new_familys_first_final():
    finals = list(range(20, 20 + 10 * MIN_FIRST_EDITIONS, 10))
    assert new_event_prior(_first_editions(finals)) == \
        pytest.approx(tuple(np.percentile(finals, [10, 50, 90])))


def test_families_seen_before_the_break_and_too_few_first_editions_say_nothing():
    finals = [100] * MIN_FIRST_EDITIONS
    old = _first_editions([5000] * 10, first_year=NEW_SINCE - 3).assign(
        family=lambda d: 'Old' + d['family'])
    assert new_event_prior(pd.concat([_first_editions(finals), old])) == (100.0, 100.0, 100.0)
    assert new_event_prior(_first_editions(finals[1:])) is None


def test_the_weight_runs_from_nothing_at_six_weeks_to_all_at_two_months():
    assert [prior_weight(T) for T in (0, 28, 42, 51, 60, 90)] == [0, 0, 0, 0.5, 1, 1]


def test_far_out_the_forecast_is_the_prior_and_never_under_the_count():
    f = Forecast(30, 12, 175, MODEL, 'size-matched')
    out = blend_new_event_prior(f, Observation(7, 60), PRIOR)
    assert (out.point, out.low, out.high) == (100, 10, 400)
    assert blend_new_event_prior(f, Observation(20, 90), PRIOR).low == 20
    half = blend_new_event_prior(f, Observation(7, 51), PRIOR)
    assert half.point == round(math.sqrt(30 * 100))
    for obs, prior in ((Observation(7, 42), PRIOR), (Observation(7, 60), None)):
        assert blend_new_event_prior(f, obs, prior) is f


def test_only_an_event_with_no_past_final_takes_the_prior():
    fitted = Fitted(model=_Model((30, 12, 175)), new_event_prior=PRIOR)
    new = forecast_event(Event('Harbor Open'), Observation(7, 60), fitted, [])
    assert (new.point, new.low, new.high, new.raw_point) == (100, 10, 400, 30)
    assert forecast_event(Event('Harbor Open'), Observation(7, 60), fitted, None).point == 30
    assert forecast_event(Event('Harbor Open'), Observation(7, 60), fitted, [200]).point != 100
