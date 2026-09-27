"""Every published or graded forecast goes through forecast_event.

The site, the backtest and the window grade used to call the engines and
the plausibility clamp each in their own way, so what was graded could drift
from what was published. Now only forecast/ may touch them; model/ is the
engine itself (recalibration re-runs its own nowcast), and tests exercise
the pieces directly.
"""
import ast
import os

import pytest

from forecast import Event, Fitted, Observation, choose_route, forecast_event
from forecast.routes import HISTORICAL_AVG, MODEL, PACE, WINDOW

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINES = {'predict_nowcast', 'predict_with_lognormal_ci',
           'window_decayed_estimate', 'apply_plausibility_clamp'}
ALLOWED = ('forecast/', 'model/', 'tests/')
SKIP_DIRS = {'.git', '.venv', 'node_modules', '__pycache__'}


def _sources():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith('.py'):
                path = os.path.join(dirpath, name)
                yield os.path.relpath(path, ROOT).replace(os.sep, '/'), path


def engine_uses(tree):
    """Line numbers where the tree names an engine: a call, a reference or an import."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in ENGINES:
            yield node.lineno
        elif isinstance(node, ast.Attribute) and node.attr in ENGINES:
            yield node.lineno
        elif isinstance(node, ast.ImportFrom):
            if any(alias.name in ENGINES for alias in node.names):
                yield node.lineno


def test_only_the_forecast_package_calls_the_engines():
    offenders = []
    for rel, path in _sources():
        if rel.startswith(ALLOWED):
            continue
        with open(path, encoding='utf-8') as fh:
            tree = ast.parse(fh.read(), filename=rel)
        offenders += [f"{rel}:{line}" for line in engine_uses(tree)]
    assert offenders == [], "call forecast.forecast_event instead: " + ", ".join(offenders)


def test_the_guard_sees_calls_references_and_imports():
    src = ("from ratio_model import predict_with_lognormal_ci\n"
           "m.predict_nowcast(1, 2, 'x')\n"
           "f = apply_plausibility_clamp\n")
    assert sorted(engine_uses(ast.parse(src))) == [1, 2, 3]


class _Model:
    """Stands in for the nowcast model: a fixed answer and a tier."""
    _last_tier = 'family'

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def predict_nowcast(self, count, T, family, **kw):
        self.calls.append((count, T, family, kw))
        return self.answer


RATIOS = {'Harbor Open': {0: [1.2, 1.25, 1.3], 28: [2.0, 2.1, 2.2]}}


def test_roster_events_take_the_model_until_the_window_opens():
    fitted = Fitted(model=_Model((200, 180, 230)), ratios=RATIOS)
    ev = Event('Harbor Open', window_len=3)
    assert choose_route(ev, Observation(100, 28), fitted, [150]) == MODEL
    assert choose_route(ev, Observation(100, 0, 1), fitted, [150]) == WINDOW
    single = Event('Harbor Open')
    assert choose_route(single, Observation(100, 0), fitted, [150]) == MODEL


def test_metadata_events_need_history_and_pace_signal():
    fitted = Fitted(ratios=RATIOS)
    ev = Event('Harbor Open', in_roster=False, canonical='Harbor Open')
    assert choose_route(ev, Observation(40, 20), fitted, [150, 160]) == PACE
    assert choose_route(ev, Observation(40, 20), fitted, []) == HISTORICAL_AVG
    assert choose_route(ev, Observation(5, 20), fitted, [150]) == HISTORICAL_AVG, "under 10 entries"
    assert choose_route(ev, Observation(40, 120), fitted, [150]) == HISTORICAL_AVG, "too far out"


def test_model_route_passes_the_event_and_date_and_keeps_the_tier():
    model = _Model((200, 180, 230))
    ev = Event('Harbor Open', event_start='2026-05-22', early_bird_deadline='2026-04-01')
    out = forecast_event(ev, Observation(100, 28), Fitted(model=model), [150, 160, 170],
                         as_of='2026-04-24')
    assert (out.point, out.low, out.high, out.route, out.tier) == (200, 180, 230, MODEL, 'family')
    assert model.calls == [(100, 28, 'Harbor Open',
                            {'early_bird_deadline': '2026-04-01',
                             'event_start_date': '2026-05-22', 'as_of': '2026-04-24'})]


def test_a_declining_model_falls_back_to_the_ratio_model_only_when_one_was_fitted():
    ev, obs = Event('Harbor Open'), Observation(100, 28)
    declines = _Model((None, None, None))
    assert forecast_event(ev, obs, Fitted(model=declines), None) is None
    out = forecast_event(ev, obs, Fitted(model=declines, ratios=RATIOS), None)
    assert out.route == MODEL and out.point > 100


def test_the_clamp_runs_last_and_floors_at_the_count():
    ev = Event('Harbor Open')
    low_model = Fitted(model=_Model((90, 80, 120)))
    raw = forecast_event(ev, Observation(100, 7), low_model, None)
    assert raw.point == 90, "no history: the raw model is graded"
    out = forecast_event(ev, Observation(100, 7), low_model, [150, 160, 170])
    assert (out.point, out.raw_point) == (100, 90)
    assert out.low <= out.point <= out.high


def test_the_window_route_decays_toward_the_live_count():
    ev = Event('Harbor Open', window_len=3)
    fitted = Fitted(ratios=RATIOS)
    first = forecast_event(ev, Observation(100, 0, 0), fitted, [])
    last = forecast_event(ev, Observation(100, 0, 2), fitted, [])
    assert first.route == WINDOW and first.tier is None
    assert first.point > last.point >= 100


def test_pace_stays_inside_the_band_around_past_finals():
    ev = Event('Somewhere', in_roster=False, canonical='Harbor Open',
               names=('Somewhere', 'Harbor Open'))
    out = forecast_event(ev, Observation(400, 28), Fitted(ratios=RATIOS), [100, 120])
    assert out.route == PACE
    assert out.point == 180, "max(history) * 1.5"


@pytest.mark.parametrize("history, expected", [
    ([], (100, 70, 130)),
    ([120], (120, 84, 156)),
    ([100, 140], (120, 100, 140)),
    ([100, 110, 120, 130, 140], (120, 104, 136)),
])
def test_historical_average(history, expected):
    ev = Event('Harbor Open', in_roster=False)
    out = forecast_event(ev, Observation(0, 60), Fitted(), history)
    assert (out.point, out.low, out.high) == expected
    assert out.route == HISTORICAL_AVG
