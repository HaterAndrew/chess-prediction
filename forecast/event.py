"""forecast_event: pick the route, run it, settle the model's forecast, clamp last."""
from dataclasses import replace

from pipeline_utils import apply_plausibility_clamp, pace_gate_ok

from forecast.known_final import anchor_known_final, ignores_last_final
from forecast.pickup import blend_pickup
from forecast.routes import (HISTORICAL_AVG, MODEL, PACE, WINDOW,
                             historical_avg_route, model_route, pace_route,
                             window_route)
from forecast.yoy_range import cap_range

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
    return run_route(choose_route(event, obs, fitted, history), event, obs, fitted,
                     history, as_of)


def shadow_forecasts(event, obs, fitted, history, as_of=None):
    """What each route that could stand in for the model would have said: the
    pace route when there are past finals to band it, and the historical average.
    Graded beside the model so the choice between them follows evidence."""
    routes = ([PACE] if history and fitted.ratios is not None else []) + [HISTORICAL_AVG]
    out = {}
    for route in routes:
        f = run_route(route, event, obs, fitted, history, as_of)
        if f is not None:
            out[route] = f
    return out


def settle_model(forecast, event, obs, fitted, history):
    """The model's forecast blended with pickup inside two weeks (forecast.pickup),
    moved toward a last final it knew nothing of (forecast.known_final), and its
    range capped (forecast.yoy_range)."""
    forecast = blend_pickup(forecast, obs)
    if ignores_last_final(forecast, event, obs, fitted, history):
        return cap_range(anchor_known_final(forecast, obs, history), obs, history,
                         fitted.yoy_arms, min_history=1)
    return cap_range(forecast, obs, history, fitted.yoy_arms)


def run_route(route, event, obs, fitted, history, as_of=None):
    """One route's forecast, or None: the model's settled (settle_model), then
    clamped as the published one is."""
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
    if route == MODEL:
        raw = settle_model(raw, event, obs, fitted, history)
    if route not in CLAMPED or history is None:
        return raw
    point, low, high = apply_plausibility_clamp(
        raw.point, raw.low, raw.high, obs.count, history, obs.days_remaining(event))
    return replace(raw, point=point, low=low, high=high)
