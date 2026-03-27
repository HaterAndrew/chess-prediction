"""
CCA day-boundary helpers.

CCA (Continental Chess Association) resets its daily entry counts at 2000 ET.
Our canonical scrape fires at 2015 ET to capture the full closed day.

A "CCA day" runs from 2000 ET on date D-1 to 2000 ET on date D.
So a scrape at 2015 ET on Mar 26 captures CCA-day Mar 26 (just closed).
A scrape at 1945 ET on Mar 26 is still in CCA-day Mar 25 (not yet closed).
"""

from datetime import date, datetime, time, timedelta

from zoneinfo import ZoneInfo

from backend.config import settings

CCA_TZ = ZoneInfo(settings.cca_timezone)


def cca_day_for(utc_dt: datetime) -> date:
    """Return the CCA-day date that a given UTC timestamp falls into.

    If local ET time is >= 2000 (day close), the CCA-day is today.
    If local ET time is < 2000, the CCA-day is yesterday (still open).
    """
    local = utc_dt.astimezone(CCA_TZ)
    close_time = time(settings.cca_day_close_hour, settings.cca_day_close_minute)
    if local.time() >= close_time:
        return local.date()
    else:
        return local.date() - timedelta(days=1)


def is_canonical_window(utc_dt: datetime, tolerance_minutes: int = 10) -> bool:
    """Return True if the given UTC time is within the canonical scrape window.

    The window is canonical_scrape_time ± tolerance_minutes (default 10).
    Must also be AFTER the day close to qualify — a scrape at 1945 ET
    is close in clock time but the day hasn't closed yet.
    """
    local = utc_dt.astimezone(CCA_TZ)
    close_time = time(settings.cca_day_close_hour, settings.cca_day_close_minute)
    if local.time() < close_time:
        return False
    canon = time(settings.canonical_scrape_hour, settings.canonical_scrape_minute)
    canon_dt = datetime.combine(local.date(), canon)
    delta = abs((local.replace(tzinfo=None) - canon_dt).total_seconds())
    return delta <= tolerance_minutes * 60
