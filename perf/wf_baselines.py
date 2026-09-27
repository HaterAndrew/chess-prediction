"""Two do-nothing forecasts the model has to beat, made from what was known on the day.

Last year: the family's most recent final. Pickup (Weatherford and Kimes
2003): this year's count plus the entries last year's edition still took
after the same horizon, c_T + (F_last - c_last,T); it lives in
forecast.pickup, since the published forecast blends it in at short
horizons. Both are scored on the records the model made, so the comparison
is like for like.
"""

def last_year_point(history):
    """The most recent prior final, or None without one."""
    return int(history[-1]) if history else None
