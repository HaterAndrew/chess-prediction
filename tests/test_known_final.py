"""A last final the model knew nothing of pulls the forecast toward it."""
import math

import pytest

from forecast import Event, Fitted, Forecast, Observation, forecast_event
from forecast.known_final import (KNOWN_FINAL_WEIGHTS, SIZE_MATCHED, anchor_known_final,
                                  ignores_last_final, known_final_weight)
from forecast.routes import MODEL


class _Model:
    def __init__(self, answer, tier=SIZE_MATCHED, recent=None):
        self.answer, self._last_tier = answer, tier
        self.family_recent_final = recent or {}

    def predict_nowcast(self, count, T, family, **kw):
        return self.answer


def _size_matched(point=18, low=10, high=40):
    return Forecast(point, low, high, MODEL, SIZE_MATCHED)


def test_the_weight_steps_down_toward_the_event():
    assert [known_final_weight(T) for T in (90, 29, 28, 15, 14, 7, 3, 1, 0)] == \
        [1.0, 1.0, 0.9, 0.9, 0.8, 0.7, 0.5, 0.3, 0.3]
    assert KNOWN_FINAL_WEIGHTS[-1][0] is None


def test_the_point_moves_in_log_space_and_the_range_with_it():
    out = anchor_known_final(_size_matched(), Observation(7, 3), [150, 271])
    point = math.exp(0.5 * math.log(271) + 0.5 * math.log(18))
    scale = point / 18
    assert (out.point, out.low, out.high) == (round(point), round(10 * scale), round(40 * scale))


def test_never_below_the_count():
    out = anchor_known_final(_size_matched(), Observation(300, 60), [271])
    assert (out.point, out.low) == (300, 300)


def test_it_fires_on_a_size_matched_forecast_with_a_last_final():
    assert ignores_last_final(_size_matched(), Event('Harbor Open'), Observation(7, 60),
                              Fitted(model=_Model(None)), [271])


@pytest.mark.parametrize('forecast, obs, recent, history', [
    (_size_matched(), Observation(7, 60), {}, []),
    (_size_matched(), Observation(7, 60), {}, None),
    (_size_matched(), Observation(0, 60), {}, [250, 0]),
    (_size_matched(point=0), Observation(0, 60), {}, [271]),
    (Forecast(18, 10, 40, MODEL, 'family-alias'), Observation(7, 60), {}, [271]),
    (Forecast(18, 10, 40, MODEL, 'family-direct'), Observation(7, 60), {}, [271]),
    (_size_matched(), Observation(7, 7, pickup=240), {}, [271]),
    (_size_matched(), Observation(7, 60), {'Harbor Open': 260}, [271]),
])
def test_it_leaves_every_other_forecast_alone(forecast, obs, recent, history):
    fitted = Fitted(model=_Model(None, recent=recent))
    assert not ignores_last_final(forecast, Event('Harbor Open'), obs, fitted, history)


def test_the_model_route_anchors_then_caps_with_one_past_final():
    fitted = Fitted(model=_Model((18, 10, 40)), yoy_arms=(0.2, 0.1))
    out = forecast_event(Event('Harbor Open'), Observation(7, 60), fitted, [271])
    assert (out.point, out.low, out.high, out.raw_point) == \
        (271, round(271 * math.exp(-0.2)), round(271 * math.exp(0.1)), 18)
    trained = Fitted(model=_Model((18, 10, 40), recent={'Harbor Open': 260}),
                     yoy_arms=(0.2, 0.1))
    assert forecast_event(Event('Harbor Open'), Observation(7, 60), trained, [271]).point < 271
