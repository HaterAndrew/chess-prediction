"""Inside two weeks the model's point is averaged with pickup in log space.

Pickup is this year's count plus what the family's last edition took after
the same horizon. The walk-forward chose the weight on earlier seasons only;
past two weeks the model stands alone.
"""
from types import SimpleNamespace

import pandas as pd

from forecast import Event, Fitted, Forecast, Observation, forecast_event
from forecast.pickup import PICKUP_HORIZON, blend_pickup, pickup_point
from forecast.routes import MODEL


class _Model:
    _last_tier = 'family'

    def __init__(self, answer):
        self.answer = answer

    def predict_nowcast(self, count, T, family, **kw):
        return self.answer


def _model(point=200, low=180, high=230):
    return Forecast(point, low, high, MODEL, 'family')


def test_the_point_is_the_geometric_mean_and_the_range_moves_with_it():
    out = blend_pickup(_model(), Observation(100, 7, pickup=162))
    assert (out.point, out.low, out.high) == (180, 162, 207)


def test_only_inside_the_horizon_and_with_a_pickup():
    f = _model()
    for obs in (Observation(100, PICKUP_HORIZON + 1, pickup=162), Observation(100, 0, pickup=162),
                Observation(100, 7), Observation(100, 7, pickup=0)):
        assert blend_pickup(f, obs) is f
    assert blend_pickup(f, Observation(100, PICKUP_HORIZON, pickup=162)).point == 180


def test_nothing_falls_below_the_count():
    out = blend_pickup(_model(), Observation(190, 3, pickup=150))
    assert (out.point, out.low, out.high) == (190, 190, 199)


def test_the_model_route_blends_before_the_clamp_and_keeps_its_raw_point():
    fitted = Fitted(model=_Model((200, 180, 230)))
    out = forecast_event(Event('Harbor Open'), Observation(100, 7, pickup=162), fitted, None)
    assert (out.point, out.raw_point, out.route) == (180, 200, MODEL)


def test_pickup_reads_the_last_edition_at_the_same_horizon():
    prior = pd.DataFrame({'tid': [1, 2], 'final_count': [150, 180]})
    counts = {(2, 7): 120, (1, 7): 100}

    def count_of(tid, T):
        return SimpleNamespace(count=counts.get((tid, T)))
    assert pickup_point(100, 7, prior, count_of) == 160, "100 + (180 - 120)"
    assert pickup_point(100, 3, prior, count_of) is None, "last edition unseen at T-3"
    assert pickup_point(100, 7, prior.iloc[0:0], count_of) is None
