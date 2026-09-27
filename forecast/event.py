"""forecast_event: pick the route, run it, clamp last."""
from dataclasses import replace

from pipeline_utils import apply_plausibility_clamp, pace_gate_ok

from forecast.routes import (HISTORICAL_AVG, MODEL, PACE, WINDOW,
                             historical_avg_route, model_route, pace_route,
                             window_route)

# Routes whose output passes through the plausibility clamp. The pace route
# keeps to its own band and the historical average is history already.
CLAMPED = frozenset({MODEL, WINDOW})


def choose_route(event, obs, fitted, history):
    """The route a forecast takes.

    A roster event goes to the model, or to the window route once its event
    has started and online entries are still open. An event known only from
    metadata extrapolates its live pace when the count carries signal, and
    otherwise publishes its historical average.
    """
    if event.in_roster:
        return WINDOW if obs.days_to_start == 0 and event.window_len > 0 else MODEL
    if history and pace_gate_ok(obs.count, obs.days_to_start, fitted.curve_for(event.family)):
        return PACE
    return HISTORICAL_AVG


def forecast_event(event, obs, fitted, history, as_of=None):
    """The published forecast for one event on one date.

    history is the list of the family's past finals the clamp and the
    metadata routes read. None skips the clamp, for grading the raw model.
    Returns None when the route has nothing to say.
    """
    route = choose_route(event, obs, fitted, history)
    if route == MODEL:
        raw = model_route(event, obs, fitted, as_of)
    elif route == WINDOW:
        raw = window_route(event, obs, fitted)
    elif route == PACE:
        raw = pace_route(event, obs, fitted, history)
    else:
        raw = historical_avg_route(history)
    if raw is None:
        return None
    raw = replace(raw, raw_point=raw.point)
    if route not in CLAMPED or history is None:
        return raw
    point, low, high = apply_plausibility_clamp(
        raw.point, raw.low, raw.high, obs.count, history, obs.days_remaining(event))
    return replace(raw, point=point, low=low, high=high)
