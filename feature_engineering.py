"""
Feature engineering for chess tournament registration prediction.

Provides day-of-week, holiday proximity, and early-bird deadline features
as lightweight adjustment factors for the N5v4_Final ratio-based model.
"""

from datetime import datetime, date, timedelta


def _to_date(d):
    """Convert various date-like inputs to a date object."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        return datetime.strptime(d[:10], "%Y-%m-%d").date()
    # pandas Timestamp
    if hasattr(d, 'date'):
        return d.date()
    raise ValueError(f"Cannot convert {type(d)} to date")


def day_of_week_features(dt):
    """Return day-of-week features for a given date.

    Returns dict with:
        day_of_week: int 0 (Monday) through 6 (Sunday)
        is_weekend: bool (Saturday or Sunday)
    """
    d = _to_date(dt)
    dow = d.weekday()
    return {
        'day_of_week': dow,
        'is_weekend': dow >= 5,
    }


# ── US holidays (fixed-date and rule-based) ──

def _us_holidays_for_year(year):
    """Return a list of (date, name) for major US holidays in a given year."""
    holidays = []

    # New Year's Day — Jan 1
    holidays.append((date(year, 1, 1), "New Year"))

    # Presidents Day — 3rd Monday of February
    feb1 = date(year, 2, 1)
    # Find first Monday in Feb
    first_mon = feb1 + timedelta(days=(7 - feb1.weekday()) % 7)
    presidents = first_mon + timedelta(weeks=2)
    holidays.append((presidents, "Presidents Day"))

    # Memorial Day — last Monday of May
    may31 = date(year, 5, 31)
    memorial = may31 - timedelta(days=(may31.weekday()) % 7)
    # weekday() for Monday is 0 — if May 31 is Monday, that's it;
    # otherwise step back to the previous Monday
    if may31.weekday() != 0:
        memorial = may31 - timedelta(days=may31.weekday())
    holidays.append((memorial, "Memorial Day"))

    # Independence Day — Jul 4
    holidays.append((date(year, 7, 4), "Independence Day"))

    # Labor Day — 1st Monday of September
    sep1 = date(year, 9, 1)
    labor = sep1 + timedelta(days=(7 - sep1.weekday()) % 7)
    if sep1.weekday() == 0:
        labor = sep1
    holidays.append((labor, "Labor Day"))

    # Thanksgiving — 4th Thursday of November
    nov1 = date(year, 11, 1)
    first_thu = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    thanksgiving = first_thu + timedelta(weeks=3)
    holidays.append((thanksgiving, "Thanksgiving"))

    # Christmas — Dec 25
    holidays.append((date(year, 12, 25), "Christmas"))

    return holidays


def holiday_proximity(dt):
    """Return the number of days to the nearest US holiday.

    Checks holidays in the current year and adjacent years to handle
    year boundaries correctly.

    Returns dict with:
        days_to_nearest_holiday: int (0 = on a holiday)
        nearest_holiday: str name of the nearest holiday
    """
    d = _to_date(dt)
    # Check current year and neighbors for boundary cases (late Dec / early Jan)
    all_holidays = []
    for y in [d.year - 1, d.year, d.year + 1]:
        all_holidays.extend(_us_holidays_for_year(y))

    best_dist = 999
    best_name = ""
    for h_date, h_name in all_holidays:
        dist = abs((d - h_date).days)
        if dist < best_dist:
            best_dist = dist
            best_name = h_name

    return {
        'days_to_nearest_holiday': best_dist,
        'nearest_holiday': best_name,
    }


def early_bird_features(current_date, early_bird_deadline):
    """Return features related to the early-bird registration deadline.

    Args:
        current_date: the prediction date
        early_bird_deadline: the early-bird cutoff date (or None)

    Returns dict with:
        days_to_early_bird: int (positive = before deadline, negative = after)
        is_before_deadline: bool
    If early_bird_deadline is None, returns neutral values.
    """
    if early_bird_deadline is None:
        return {
            'days_to_early_bird': None,
            'is_before_deadline': None,
        }

    cd = _to_date(current_date)
    eb = _to_date(early_bird_deadline)
    delta = (eb - cd).days  # positive means deadline is in the future

    return {
        'days_to_early_bird': delta,
        'is_before_deadline': delta > 0,
    }


def compute_all_features(current_date, event_start_date, early_bird_deadline=None):
    """Combine all feature functions into a single feature dict.

    Args:
        current_date: date of prediction
        event_start_date: tournament start date
        early_bird_deadline: optional early-bird cutoff date

    Returns a flat dict with all feature keys.
    """
    features = {}
    features.update(day_of_week_features(event_start_date))
    features.update(holiday_proximity(event_start_date))
    features.update(early_bird_features(current_date, early_bird_deadline))
    return features


def compute_adjustment_factor(features, days_remaining):
    """Translate raw features into a multiplicative adjustment factor.

    Design rationale:
    - Tournaments near major holidays tend to draw fewer players (travel
      conflicts), so we apply a small downward adjustment.
    - Weekend event starts get a slight boost (easier travel logistics).
    - Approaching early-bird deadlines drive bulk registration; if the
      deadline is within 7 days and hasn't passed, boost the prediction.
    - After the early-bird deadline, late registrants trickle in more
      slowly, so apply a small damping factor.

    Returns a float multiplier (1.0 = no adjustment).
    """
    adj = 1.0

    # ── Holiday proximity effect ──
    # Events within 3 days of a major holiday see ~3-5% fewer registrants
    # due to travel/family conflicts. Effect tapers linearly out to 10 days.
    days_to_holiday = features.get('days_to_nearest_holiday')
    if days_to_holiday is not None:
        if days_to_holiday <= 3:
            adj *= 0.96  # 4% reduction
        elif days_to_holiday <= 7:
            adj *= 0.98  # 2% reduction
        elif days_to_holiday <= 10:
            adj *= 0.99  # 1% reduction

    # ── Weekend start boost ──
    # Tournaments starting on weekends are slightly easier to attend
    if features.get('is_weekend'):
        adj *= 1.02  # 2% boost

    # ── Early-bird deadline effects ──
    days_to_eb = features.get('days_to_early_bird')
    if days_to_eb is not None:
        is_before = features.get('is_before_deadline', False)
        if is_before and days_to_eb <= 7:
            # Approaching deadline drives bulk registration — boost prediction
            # Stronger effect closer to deadline
            if days_to_eb <= 2:
                adj *= 1.06  # 6% boost in final 2 days before EB deadline
            elif days_to_eb <= 5:
                adj *= 1.04  # 4% boost in the week before
            else:
                adj *= 1.02  # 2% boost
        elif not is_before and days_to_eb is not None:
            # After early-bird deadline: registration pace slows
            days_past = abs(days_to_eb)
            if days_past <= 14:
                adj *= 0.98  # 2% reduction in first 2 weeks after EB
            # Further out, the effect dissipates — no adjustment

    return adj
