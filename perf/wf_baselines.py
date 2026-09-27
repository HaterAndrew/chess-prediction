"""Two do-nothing forecasts the model has to beat, made from what was known on the day.

Last year: the family's most recent final. Pickup (Weatherford and Kimes
2003): this year's count plus the entries last year's edition still took
after the same horizon, c_T + (F_last - c_last,T). Both are scored on the
records the model made, so the comparison is like for like.
"""
from corpus.coverage import count_as_of


def last_year_point(history):
    """The most recent prior final, or None without one."""
    return int(history[-1]) if history else None


def pickup_point(count, T, prior, curve_of, bound_of):
    """count + (last final - last edition's count at T), or None when that count is unknown.

    prior: the family's finished editions before this one, oldest first.
    curve_of(tid) and bound_of(tid) give an edition's curve and export bound.
    """
    if prior.empty:
        return None
    last = prior.iloc[-1]
    seen = count_as_of(curve_of(last['tid']), T, exact_until_T=bound_of(last['tid']))
    if seen.count is None:
        return None
    return int(count + int(last['final_count']) - seen.count)
