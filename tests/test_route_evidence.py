"""Stand-in routes are graded beside the model; one earns a bucket only on evidence."""
import numpy as np

from forecast import Event, Fitted, Observation, shadow_forecasts
from forecast.routes import HISTORICAL_AVG, NO_HISTORY_MEAN
from perf.route_evidence import (COUNT_BANDS, MODEL, STAND_IN, TOO_FEW, band_of,
                                 route_evidence)


def _records(n, stand_in_width, model_width=0.3, T=7, count=20, n_history=4, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        final = int(rng.integers(80, 400))
        point = final * np.exp(rng.normal(0, 0.05))
        rows.append({'tid': i, 'family': f'F{i}', 'T': T, 'count': count, 'n_history': n_history,
                     'final': final, 'point': point,
                     'low': point * np.exp(-model_width), 'high': point * np.exp(model_width),
                     'pace_point': None, 'pace_low': None, 'pace_high': None,
                     'hist_point': point, 'hist_low': point * np.exp(-stand_in_width),
                     'hist_high': point * np.exp(stand_in_width)})
    return rows


def test_bands():
    assert [band_of(c, COUNT_BANDS) for c in (1, 9, 10, 99, 100, 5000)] == \
        ['1-9', '1-9', '10-29', '30-99', '100+', '100+']


def test_a_stand_in_earns_a_bucket_only_by_more_than_a_standard_error():
    tighter = route_evidence(_records(40, stand_in_width=0.12))
    assert [(r['route'], r['band'], r['count_band'], r['history'], r['verdict']) for r in tighter] == \
        [(HISTORICAL_AVG, 'short', '10-29', '3+', STAND_IN)]
    wider = route_evidence(_records(40, stand_in_width=0.6))
    assert wider[0]['verdict'] == MODEL and wider[0]['lis_diff'] < 0
    assert route_evidence(_records(10, stand_in_width=0.12))[0]['verdict'] == TOO_FEW
    assert route_evidence([]) == []


def test_shadows_are_the_stand_ins_that_can_speak():
    fitted = Fitted(model=None)
    shadows = shadow_forecasts(Event('Harbor Open'), Observation(40, 14), fitted, [180, 200, 220])
    assert list(shadows) == [HISTORICAL_AVG], "no pace route without a fitted ratio model"
    assert (shadows[HISTORICAL_AVG].point, shadows[HISTORICAL_AVG].low) == (200, 180)
    empty = shadow_forecasts(Event('New Open'), Observation(40, 14), fitted, [])
    assert empty[HISTORICAL_AVG].point == NO_HISTORY_MEAN
