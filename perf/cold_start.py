"""Cold start: an event forecast as if no model had trained on its family.

The walk-forward holds 11 events with 0-1 prior editions, too few to judge a
change made for them. In a cold-start run every graded event is forecast
under a family name nothing trained on, so its ratios come from the
size-matched tier as a new event's do. FINALS keeps the family's past finals:
an event whose earlier editions left no registration curve. NONE removes
them: a brand-new event. Neither has a pickup, which reads the last
edition's curve. The record keeps the event's own family, so standard errors
still resample real families.
"""
from dataclasses import replace

FINALS = 'finals'
NONE = 'none'
MODES = (FINALS, NONE)

UNTRAINED = '__cold_start__'


def disguise(event, history, pickup, mode):
    """The event, its past finals and its pickup as the forecaster sees them in `mode`."""
    if mode is None:
        return event, history, pickup
    if mode not in MODES:
        raise ValueError(f"cold start is one of {MODES}, not {mode!r}")
    hidden = replace(event, family=UNTRAINED, canonical=UNTRAINED, names=(UNTRAINED,))
    return hidden, (history if mode == FINALS else []), None
