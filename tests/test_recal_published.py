"""Inside two weeks the recalibration sizes the range around the point the site publishes."""
import math

import pandas as pd
import pytest

from forecast import Forecast, Observation
from forecast.cohort_pickup import pickup_gains
from forecast.pickup import blend_pickup
from forecast.routes import MODEL
from model.recal_factors import ci_scale, published_center
from model.recal_residuals import Residual, residual


def _res(actual=200, point=150, pickup=180, count=120, halfw=0.2):
    return Residual(err_pct=(point - actual) / actual, log_actual=math.log(actual),
                    log_point=math.log(point), log_halfw=halfw, ci_hit=1, last_reg=None,
                    in_sample=False, year=2026, count=count, pickup=pickup)


def test_the_center_is_the_published_point():
    r = _res()
    published = blend_pickup(Forecast(150 * 1.1, 100, 250, MODEL), Observation(120, 7, pickup=180))
    assert math.exp(published_center(r, math.log(1.1), 7)) == pytest.approx(published.point, abs=0.5)


def test_outside_the_blend_the_center_is_the_models():
    model = math.log(150) + math.log(1.1)
    for r, T in ((_res(), 28), (_res(pickup=None), 7), (_res(), None)):
        assert published_center(r, math.log(1.1), T) == pytest.approx(model)


def test_never_under_the_count():
    r = _res(point=100, pickup=110, count=130)
    assert math.exp(published_center(r, 0.0, 3)) == pytest.approx(130)


def test_a_blend_that_lands_on_the_final_asks_for_a_narrower_range():
    records = [_res(actual=a, point=a * 0.8, pickup=a * 1.25, count=10) for a in range(100, 120)]
    assert ci_scale(records, 1.0, 0.8, T=7) == pytest.approx(0.0, abs=1e-9)
    assert ci_scale(records, 1.0, 0.8, T=28) == pytest.approx(math.log(1.25) / 0.2)


class _Model:
    _recal_bias, _recal_ci, _fit_tids = {}, {}, set()

    def predict_nowcast(self, count, T, family, **kw):
        return 150, 100, 250


def test_a_residual_carries_the_pickup_its_forecast_would_blend():
    daily = pd.DataFrame({'tid': [2, 2], 'T': [8, 7], 'cum_regs': [110, 120]})
    row = pd.Series({'tid': 2, 'family': 'Harbor Open', 'final_count': 200,
                     'tournament_year': 2026})
    r = residual(_Model(), row, daily, 7, loo=False, gains={(2, 7): 60})
    assert (r.count, r.pickup) == (120, 180)
    assert residual(_Model(), row, daily, 7, loo=False).pickup is None


def test_the_gain_is_what_the_last_edition_took_after_the_horizon():
    summary = pd.DataFrame({
        'tid': [1, 2, 3], 'family': ['Harbor Open'] * 3, 'tournament_year': [2024, 2025, 2026],
        'final_count': [150, 200, 210], 'is_online': False, 'is_covid': False,
        'has_timestamps': True})
    daily = pd.DataFrame({'tid': [1, 2, 2], 'T': [7, 14, 7], 'cum_regs': [90, 100, 140]})
    cohort = summary[summary['tid'] == 3]
    assert pickup_gains(cohort, summary, daily, (14, 7, 3)) == {(3, 14): 100, (3, 7): 60,
                                                                (3, 3): 60}
    assert pickup_gains(summary[summary['tid'] == 1], summary, daily, (7,)) == {}
