"""A known last final, for an event the model holds no final for.

The model anchors on a family's most recent final only when that edition
trained it, which takes a registration curve. An event whose past editions
have finals but no curves falls to the size-matched tier and extrapolates
its count: Washington Chess Congress 2023 was forecast at 18 at T-60, with
a last final of 271 and a final of 249. anchor_known_final moves such a
forecast toward the last final in log space, one weight per horizon, and
the range moves with the point. The weights score best over every season so
far on the walk-forward with each event forecast as if its family were new
and its past finals kept (perf.cold_start); chosen season by season on
earlier seasons only, they settled within 0.2 of these and lowered both
scores in each of 2024, 2025 and 2026 (#187).

A pickup already carries the last edition, and an alias family's final
belongs to another event, so neither case is anchored.
"""
import math

# (days to start at most, weight on the last final); None covers every
# longer horizon.
KNOWN_FINAL_WEIGHTS = ((1, 0.3), (3, 0.5), (7, 0.7), (14, 0.8), (28, 0.9), (None, 1.0))
# The nowcast model's tier when it found no ratios for the family or an alias.
SIZE_MATCHED = 'size-matched'


def known_final_weight(days_to_start):
    """The weight on the last final at this horizon."""
    return next(w for limit, w in KNOWN_FINAL_WEIGHTS
                if limit is None or days_to_start <= limit)


def ignores_last_final(forecast, event, obs, fitted, history):
    """True when history holds a last final the forecast knows nothing of.

    A last final of zero is a recording gap, not a size, and is not anchored.
    """
    recent = getattr(fitted.model, 'family_recent_final', None) or {}
    return (bool(history) and (history[-1] or 0) > 0 and forecast.tier == SIZE_MATCHED
            and not obs.pickup and not recent.get(event.family) and forecast.point > 0)


def anchor_known_final(forecast, obs, history):
    """The forecast moved toward the last final, never below the count."""
    w = known_final_weight(obs.days_to_start)
    anchor = max(history[-1], obs.count)
    return forecast.moved_to(math.exp(w * math.log(anchor)
                                      + (1 - w) * math.log(forecast.point)), obs.count)
