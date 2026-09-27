"""The four routes to a forecast.

Each takes what was known on the forecast date and returns a Forecast, or
None when it has nothing to say. The route names are the prediction_source
labels the site and the forecast ledger publish.
"""
import numpy as np

from prediction_window import window_decayed_estimate
from ratio_model import predict_with_lognormal_ci

from forecast.types import Forecast

MODEL = 'model'
WINDOW = 'model_online_window'
PACE = 'metadata_pace'
HISTORICAL_AVG = 'metadata_historical_avg'

# The historical average of an event with no finished edition to average.
NO_HISTORY_MEAN = 100
# The pace route keeps its forecast inside this band around past finals, so a
# sparse far-out count cannot scale up into an absurd number.
PACE_BAND = (0.6, 1.5)


def model_route(event, obs, fitted, as_of):
    """The nowcast model; the ratio model when it declines and one was fitted."""
    point, low, high = fitted.model.predict_nowcast(
        obs.count, obs.days_to_start, event.family,
        early_bird_deadline=event.early_bird_deadline,
        event_start_date=event.event_start, as_of=as_of)
    tier = getattr(fitted.model, '_last_tier', None)
    if point is None:
        if fitted.ratios is None:
            return None
        point, low, high = predict_with_lognormal_ci(
            obs.count, obs.days_to_start, event.family, fitted.ratios)
    return Forecast(point, low, high, MODEL, tier)


def window_route(event, obs, fitted):
    """Inside the post-start registration window.

    The ratio model's T=0 bucket is the whole count-at-start to final
    multiplier; it decays toward the live count as registration close nears.
    The nowcast model's finest bucket is T-1, so it would over-extrapolate here.
    """
    p0, lo0, hi0 = predict_with_lognormal_ci(obs.count, 0, event.family, fitted.ratios)
    point, low, high = window_decayed_estimate(
        obs.count, p0, lo0, hi0, obs.days_into_window, event.window_len)
    return Forecast(point, low, high, WINDOW)


def pace_route(event, obs, fitted, history):
    """Live pace off the roster: the ratio model under the name it trained on."""
    ratio_family = next((n for n in event.names if n in fitted.ratios), event.canonical)
    p, lo, hi = predict_with_lognormal_ci(
        obs.count, obs.days_to_start, ratio_family, fitted.ratios)
    band_lo, band_hi = min(history) * PACE_BAND[0], max(history) * PACE_BAND[1]
    point, low, high = (int(min(max(v, band_lo), band_hi)) for v in (p, lo, hi))
    if high <= low:
        low, high = int(min(history)), int(max(history))
    return Forecast(point, low, high, PACE)


def historical_avg_route(history):
    """The mean of past finals, with a range from their spread."""
    history = history or []
    mean = np.mean(history) if history else NO_HISTORY_MEAN
    if len(history) >= 5:
        low, high = int(np.percentile(history, 10)), int(np.percentile(history, 90))
    elif len(history) >= 2:
        low, high = int(min(history)), int(max(history))
    else:
        low, high = int(mean * 0.7), int(mean * 1.3)
    return Forecast(int(mean), low, high, HISTORICAL_AVG)
