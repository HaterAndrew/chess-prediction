"""Shared helpers used across the daily pipeline scripts.

Single source of truth for predicates that the perf eval, website model
fitting, recalibration, and walk-in multiplier scripts must all agree on.
"""
import pandas as pd


def is_event_complete(end_date, today=None):
    """A tournament is 'complete' iff its event end_date is strictly in the past.

    Mid-event days (today == end_date) count as in-progress: late entries and
    walk-ins can still arrive on the last day, so summary.final_count is not
    yet authoritative.

    Returns False for NaT / None / unparseable end_dates (unknown = not safe
    to treat as complete).
    """
    if end_date is None:
        return False
    end = pd.to_datetime(end_date, errors='coerce')
    if pd.isna(end):
        return False
    if today is None:
        today = pd.Timestamp.now().normalize()
    return end < today
