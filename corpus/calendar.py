"""When each event starts and ends, as far as the corpus can say."""
import pandas as pd


def meta_dates(meta):
    """(family, year) -> (start, end) from the metadata; a later row wins, as in reanchoring."""
    starts = pd.to_datetime(meta['start_date'], errors='coerce')
    ends = pd.to_datetime(meta['end_date'], errors='coerce')
    return {(fam, int(yr)): (s, e)
            for fam, yr, s, e in zip(meta['family'], meta['year'], starts, ends)}


def event_calendar(summary, meta):
    """One row per summary event: tid, start and end.

    Dates come from the metadata row for the (family, year). An event with no
    metadata has no start; its end is the day of its last registration, which
    the export stamps at the event itself, or failing that the last day of its
    year. An event with none of these has no end and never counts as finished.
    """
    dates = meta_dates(meta)
    last_reg = pd.to_datetime(summary['last_reg'], errors='coerce').dt.normalize()
    rows = []
    for tid, fam, yr, lr in zip(summary['tid'], summary['family'],
                                summary['tournament_year'], last_reg):
        key = (fam, int(yr)) if pd.notna(yr) else None
        start, end = dates.get(key, (pd.NaT, pd.NaT))
        rows.append({'tid': tid, 'start': start, 'end': _first_known(end, lr, _year_end(yr))})
    return pd.DataFrame(rows, columns=['tid', 'start', 'end'])


def _year_end(year):
    return pd.Timestamp(int(year), 12, 31) if pd.notna(year) and year > 0 else pd.NaT


def _first_known(*dates):
    return next((d for d in dates if pd.notna(d)), pd.NaT)
