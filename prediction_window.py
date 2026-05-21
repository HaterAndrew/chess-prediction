"""Post-start online-registration window.

CCA majors run concurrent 5-day / 4-day / 3-day / 2-day schedules that all
finish on the same final weekend. Online entries keep arriving after the
5-day schedule's start_date — right up to the start of the 2-day schedule,
the day before the event ends. The prediction model has to keep projecting a
final count through that window instead of freezing on the live count the
moment the 5-day schedule begins.

This module isolates the two pure pieces of that logic so they can be unit
tested without running the full 04d pipeline:

  * registration_close_date  — when online registration actually closes
  * window_decayed_estimate  — projecting the final count from inside the window
"""

import pandas as pd


def registration_close_date(event_date, event_end_date):
    """Date online registration closes — distinct from the event start.

    Rule: registration_close = end_date - 1 day. The 2-day schedule (the last
    online entry point) starts the day before the event ends. Checked against
    the last four Chicago Opens, where the final registration timestamp landed
    within a day of end_date - 1 every year.

    Falls back to event_date when end_date is unknown (a single-schedule event
    registers only up to its own start). Never returns a date earlier than
    event_date. Returns None when event_date is None.
    """
    if event_date is None:
        return None
    if event_end_date is None:
        return pd.Timestamp(event_date)
    close = pd.Timestamp(event_end_date) - pd.Timedelta(days=1)
    return max(close, pd.Timestamp(event_date))


def window_decayed_estimate(current_count, t0_point, t0_lo, t0_hi,
                            days_into_window, window_len):
    """Project the final count from inside the post-start registration window.

    t0_* is the event-start (T=0) prediction triple — the full
    count-at-event-start -> final-field multiplier. As TODAY advances through
    the window toward registration close, the remaining growth shrinks; decay
    the multiplier geometrically so the estimate converges on current_count at
    close instead of drifting upward as the live count climbs.

    days_into_window: whole days since event_start (0 on the start day).
    window_len:       event_start -> registration_close span in days.

    Returns (point, ci_lower, ci_upper). Each is >= current_count — entries
    already registered cannot un-register, so the final field is never lower.
    """
    if current_count <= 0 or t0_point is None or window_len <= 0:
        return current_count, current_count, current_count
    decay = (window_len - days_into_window) / window_len
    decay = max(0.0, min(1.0, decay))

    def _project(end_value):
        if end_value is None:
            return current_count
        ratio = max(end_value / current_count, 1.0)
        return round(current_count * ratio ** decay)

    return _project(t0_point), _project(t0_lo), _project(t0_hi)
