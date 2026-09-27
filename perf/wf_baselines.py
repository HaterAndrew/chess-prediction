"""Two do-nothing forecasts the model has to beat, made from what was known on the day.

Last year: the family's most recent final. Pickup (Weatherford and Kimes
2003): this year's count plus the entries last year's edition still took
after the same horizon, c_T + (F_last - c_last,T). Both are scored on the
records the model made, so the comparison is like for like.
"""


def last_year_point(history):
    """The most recent prior final, or None without one."""
    return int(history[-1]) if history else None


def pickup_point(count, T, prior, count_of):
    """count + (last final - last edition's count at T), or None when that count is unknown.

    prior: the family's finished editions before this one, oldest first.
    count_of(tid, T) reads an edition's count as of T days out (a CountAsOf).
    """
    if prior.empty:
        return None
    last = prior.iloc[-1]
    seen = count_of(last['tid'], T)
    if seen.count is None:
        return None
    return int(count + int(last['final_count']) - seen.count)
