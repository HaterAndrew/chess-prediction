"""A prior for an event with no past final, from the first editions before it.

Far out, a brand-new event's count is a handful of entries and the model
extrapolates it: Continental Class 2023 had 7 entries at T-60, was forecast
at 30 and drew 198. Families first seen after the 2020-21 break show what a
first edition draws; new_event_prior takes the 10th, 50th and 90th
percentile of their first finals, and blend_new_event_prior moves the
model's point and range to them in log space, fully from T-60 out and not
at all inside T-42.

On the walk-forward with every event forecast as if it were new and had no
past final (perf.cold_start), a weight chosen on earlier seasons only was
1.0 at T-90 and T-60 in each of 2024, 2025 and 2026, moved between 0.3 and
0.7 at T-42, and was near 0 inside four weeks, where the count says more.
Serving the prior at T-60 and beyond lowered the interval score there in
every season; one weight across the long band made T-42 and T-28 worse
(#189).
"""
import math
from dataclasses import replace

import numpy as np

# Families first seen in this season or later are new events, not gaps in the record.
NEW_SINCE = 2022
# Fewer first editions than this say nothing about a new event's size.
MIN_FIRST_EDITIONS = 15
# The prior's weight is 0 at or inside FAR_FROM[0] days and 1 at or beyond
# FAR_FROM[1], linear between.
FAR_FROM = (42, 60)


def new_event_prior(settled):
    """(p10, p50, p90) of first-edition finals, or None.

    settled: finished in-person editions with family, tournament_year and final_count.
    """
    rows = settled.dropna(subset=['final_count', 'tournament_year'])
    first = rows.sort_values('tournament_year', kind='mergesort').groupby('family').head(1)
    first = first[first['tournament_year'] >= NEW_SINCE]
    if len(first) < MIN_FIRST_EDITIONS:
        return None
    return tuple(float(v) for v in np.percentile(first['final_count'], [10, 50, 90]))


def prior_weight(days_to_start):
    """The prior's weight at this horizon."""
    near, far = FAR_FROM
    return min(max((days_to_start - near) / (far - near), 0.0), 1.0)


def blend_new_event_prior(forecast, obs, prior):
    """The forecast's point and range moved toward the prior's, never below the count."""
    w = prior_weight(obs.days_to_start)
    if prior is None or w == 0 or min(forecast.point, forecast.low, forecast.high) <= 0:
        return forecast

    def toward(target, own):
        return math.exp(w * math.log(target) + (1 - w) * math.log(own))
    p10, p50, p90 = prior
    point = max(round(toward(p50, forecast.point)), obs.count)
    return replace(forecast, point=point, low=max(round(toward(p10, forecast.low)), obs.count),
                   high=max(round(toward(p90, forecast.high)), point))
