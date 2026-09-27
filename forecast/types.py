"""What a forecast is made from, and what it returns."""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Event:
    """An edition as the forecaster sees it.

    family is the name the models were trained under. canonical and names
    matter only off the roster, where the ratio model may know the event by
    an alias: names lists the candidates in lookup order, canonical is the
    fallback when none of them trained.
    """
    family: str
    event_start: Any = None
    early_bird_deadline: Any = None
    # Days from event start to online-registration close; 0 when entries stop
    # at the start.
    window_len: int = 0
    # On the trained roster (a summary row) or known only from metadata.
    in_roster: bool = True
    canonical: Optional[str] = None
    names: tuple = ()


@dataclass(frozen=True)
class Observation:
    """What had been counted on the forecast date."""
    count: int
    days_to_start: int
    days_into_window: int = 0

    def days_remaining(self, event):
        """Days to event start, then days to registration close once it has begun."""
        if self.days_to_start > 0:
            return self.days_to_start
        return max(event.window_len - self.days_into_window, 0)


@dataclass(frozen=True)
class Fitted:
    """Everything a forecast reads that was learned from past editions."""
    model: Any = None
    ratios: Optional[dict] = None
    curves: dict = field(default_factory=dict)
    # Recalibration cohort size and diagnostics, for the run log.
    recal: Optional[dict] = None

    def curve_for(self, family):
        return self.curves.get(family, self.curves.get('__global__', {}))


@dataclass(frozen=True)
class Forecast:
    point: Any
    low: Any
    high: Any
    route: str
    tier: Optional[str] = None
    # The route's point before the plausibility clamp, so graders can count
    # how often the clamp changed a published number.
    raw_point: Any = None
