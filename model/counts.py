"""The registration count each event had reached at each chop point.

The ratio lists, the regression data, the interval calibration and
ratio_model each filtered the whole daily table once per event and took the
count at T as the largest cumulative count among that event's rows at least
T days out. This is that rule in one place, read once per event.
"""

# An event needs this many daily rows before its curve is trusted at all.
MIN_CURVE_ROWS = 5


def curve_count_at(td, T):
    """The count T days out: the largest cum_regs among rows with T' >= T,
    or None when the curve has no row that early."""
    regs = td[td['T'] >= T]
    if len(regs) == 0:
        return None
    return int(regs['cum_regs'].max())


def counts_by_event(daily, tids, chop_points):
    """{tid: {T: count}} for each event with at least MIN_CURVE_ROWS rows.

    A chop point is left out when the curve has no row that early or the
    count there is 0; an event whose curve qualifies but has no usable chop
    point maps to {}. Chop points keep the order given.
    """
    wanted = daily[daily['tid'].isin(set(tids))]
    out = {}
    for tid, td in wanted.groupby('tid', sort=False):
        if len(td) < MIN_CURVE_ROWS:
            continue
        counts = {T: curve_count_at(td, T) for T in chop_points}
        out[tid] = {T: c for T, c in counts.items() if c}
    return out
