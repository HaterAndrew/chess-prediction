"""The range is held to the year-over-year spread of finals, and only narrowed."""
import math

import numpy as np
import pandas as pd
import pytest

from forecast import Event, Fitted, Forecast, Observation, forecast_event
from forecast.fit import settled_editions
from forecast.routes import MODEL
from forecast.yoy_range import MIN_PAIRS, cap_range, yoy_arms

ARMS = (0.2, 0.1)


class _Model:
    _last_tier = 'family-direct'

    def __init__(self, answer):
        self.answer = answer

    def predict_nowcast(self, count, T, family, **kw):
        return self.answer


def _editions(changes, first=200):
    """One family per change: two editions a year apart, the second `change` times the first."""
    rows = []
    for i, change in enumerate(changes):
        rows += [{'tid': 2 * i, 'family': f'F{i}', 'tournament_year': 2024, 'final_count': first},
                 {'tid': 2 * i + 1, 'family': f'F{i}', 'tournament_year': 2025,
                  'final_count': first * change}]
    return pd.DataFrame(rows)


def _model(point=200, low=100, high=400):
    return Forecast(point, low, high, MODEL, 'family-direct')


def test_the_arms_run_from_the_median_change_to_its_tenth_and_ninetieth_percentile():
    changes = np.exp(np.linspace(-0.3, 0.2, 41))
    below, above = yoy_arms(_editions(changes))
    low, mid, high = np.percentile(np.log(changes), [10, 50, 90])
    assert (below, above) == pytest.approx((mid - low, high - mid))


def test_too_few_pairs_measure_nothing():
    assert yoy_arms(_editions([1.1] * (MIN_PAIRS - 1))) is None
    assert yoy_arms(_editions([1.1] * MIN_PAIRS)) is not None


def test_small_editions_and_long_gaps_are_not_pairs():
    wide = _editions(np.exp(np.linspace(-0.3, 0.2, 41)))
    small = _editions([5.0] * 10, first=20).assign(family=lambda d: 'S' + d['family'])
    lapsed = _editions([5.0] * 10).assign(
        family=lambda d: 'L' + d['family'],
        tournament_year=lambda d: d['tournament_year'].replace(2024, 2021))
    assert yoy_arms(pd.concat([wide, small, lapsed])) == yoy_arms(wide)


def test_an_open_season_is_settled_only_where_its_event_is_over():
    rows = pd.DataFrame({'tid': [1, 2, 3], 'tournament_year': [2025, 2026, 2026]})
    assert list(settled_editions(rows, {2}, 2026)['tid']) == [1, 2]


def test_each_side_is_held_to_its_arm_and_never_widened():
    out = cap_range(_model(), Observation(50, 60), [190, 205], ARMS)
    assert (out.point, out.low, out.high) == (200, round(200 * math.exp(-0.2)),
                                              round(200 * math.exp(0.1)))
    inside = _model(low=190, high=210)
    assert cap_range(inside, Observation(50, 60), [190, 205], ARMS) is inside
    one_side = cap_range(_model(low=190), Observation(50, 60), [190, 205], ARMS)
    assert (one_side.low, one_side.high) == (190, 221)


def test_the_low_stays_at_or_above_the_count():
    out = cap_range(_model(), Observation(180, 3), [190, 205], ARMS)
    assert (out.low, out.high) == (180, 221)


def test_an_event_without_two_past_finals_keeps_its_range():
    f = _model()
    for history in (None, [], [200]):
        assert cap_range(f, Observation(50, 60), history, ARMS) is f
    assert cap_range(f, Observation(50, 60), [190, 205], None) is f


def test_the_model_route_caps_after_the_blend_and_before_the_clamp():
    fitted = Fitted(model=_Model((200, 100, 400)), yoy_arms=ARMS)
    out = forecast_event(Event('Harbor Open'), Observation(50, 60), fitted, [190, 205])
    assert (out.point, out.low, out.high, out.raw_point) == (200, 164, 221, 200)
    blended = forecast_event(Event('Harbor Open'), Observation(100, 7, pickup=162), fitted,
                             [190, 205])
    assert (blended.point, blended.low, blended.high) == (180, 147, 199), \
        "held to the blended point's arms"
    unfitted = Fitted(model=_Model((200, 100, 400)))
    assert forecast_event(Event('Harbor Open'), Observation(50, 60), unfitted,
                          [190, 205]).low == 100
