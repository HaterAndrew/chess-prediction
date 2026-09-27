"""An event's entry count on a forecast date, from what had been seen by then.

A curve is one event's rows of (T, cum_regs), T in days before the event
start. The forecast T days out is made on start - T, so the rows known then
are those with T' >= T. The backtest used to take the nearest row within two
days either side, often a later one, which let a forecast read entries that
had not arrived yet.

Two kinds of curve. The admin export lists every registration, so a day with
no row had no new entries and the last row carries forward for as long as it
takes. The nightly scrape is a series of observations, so a gap is a missed
scrape: its last observation carries forward at most CARRY_DAYS days, or
for good once registration has closed.
"""
from dataclasses import dataclass
from typing import Optional

# How long a scraped count stands in for the days after it.
CARRY_DAYS = 3

OBSERVED = 'observed'
CARRIED = 'carried'
NOT_OPEN = 'not_open'
UNOBSERVED = 'unobserved'


@dataclass(frozen=True)
class CountAsOf:
    count: Optional[int]
    # OBSERVED: a row on the day. CARRIED: an earlier scraped row stands in.
    # NOT_OPEN: no entries yet. UNOBSERVED: the count is not known.
    basis: str


def count_as_of(curve, T, exact=True, carry_days=CARRY_DAYS, close_T=None):
    """The count T days before the start, read only from rows dated by then.

    exact: the curve lists every registration (the export); False for a
    scraped curve. close_T: the T of registration close (0 or below), after
    which a scraped count cannot change. An event with no rows at all has no
    count.
    """
    if curve.empty:
        return CountAsOf(None, UNOBSERVED)
    known = curve[curve['T'] >= T]
    if known.empty:
        # Counts never fall, so a zero seen later means zero then.
        if exact or (curve['cum_regs'] == 0).any():
            return CountAsOf(0, NOT_OPEN)
        return CountAsOf(None, UNOBSERVED)
    count = int(known['cum_regs'].max())
    last_T = int(known['T'].min())
    if exact or last_T == T:
        return CountAsOf(count, OBSERVED)
    closed = close_T is not None and last_T <= close_T
    if last_T - T <= carry_days or closed:
        return CountAsOf(count, CARRIED)
    return CountAsOf(None, UNOBSERVED)
