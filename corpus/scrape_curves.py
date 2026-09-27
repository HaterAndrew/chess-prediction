"""Registration curves built from the nightly scrape, for editions the export never saw.

The admin export stops at its snapshot (2026-03-21). 01_data_prep extends the
curves of events the export already held; an edition that opened after the
snapshot has only the scrape. Its curve is the scrape's gross entry count,
held to a running maximum, one row per scraped day, T in days before the
event start. Days after the start are left out, as the loader drops them
from export curves, and so are days with no entries, as 01_data_prep drops
them.

An edition still registering on the scrape's last day is the exception: its
curve is the lower envelope, each day the least count seen from then to the
last scrape, so it ends at the count the live card shows. Its gross count can
fall when entries are deleted (Eastern Chess Congress, 55 to 50 on
2026-09-22), and a running maximum would sit above it. No forecast is graded
or trained on an edition before it starts, so reading its later days is no
look-ahead; once it starts, its curve is the running maximum again.
"""
import pandas as pd

from corpus.labels import edition_key

CURVE_COLUMNS = ['tid', 'T', 'daily_regs', 'cum_regs', 'cum_pct']


def scrape_curves(scrape, summary, calendar, have_curve):
    """Curves for scraped editions with a start date and no curve yet.

    scrape: daily_scrape.csv rows. calendar: tid, start (corpus.calendar).
    have_curve: tids that already have a curve. Joined on the edition's name,
    commas and repeated spaces aside (corpus.labels.edition_key).
    """
    if scrape is None or scrape.empty:
        return pd.DataFrame(columns=CURVE_COLUMNS)
    editions = summary[['tid', 'tournament_name', 'final_count']].merge(calendar, on='tid')
    editions = editions[~editions['tid'].isin(have_curve) & editions['start'].notna()]
    editions = editions.assign(key=editions['tournament_name'].map(edition_key))
    last_day = pd.to_datetime(scrape['date']).max().normalize()
    rows = scrape[['tournament_name', 'date', 'entry_count']]
    rows = rows.assign(key=rows['tournament_name'].map(edition_key)).drop(columns='tournament_name')
    rows = rows.merge(editions, on='key')
    rows = rows.assign(date=pd.to_datetime(rows['date']).dt.normalize())
    rows['T'] = (rows['start'] - rows['date']).dt.days
    rows = rows[(rows['T'] >= 0) & (rows['entry_count'] > 0)]
    rows = rows.sort_values(['tid', 'T'], ascending=[True, False], kind='stable')
    rows = rows.drop_duplicates(['tid', 'T'], keep='last')
    rows['cum_regs'] = _gross_curve(rows, last_day)
    rows['daily_regs'] = rows.groupby('tid')['cum_regs'].diff().fillna(rows['cum_regs']).astype(int)
    rows['cum_pct'] = (rows['cum_regs'] / rows['final_count']).where(rows['final_count'] > 0)
    return rows[CURVE_COLUMNS].reset_index(drop=True)


def _gross_curve(rows, last_day):
    """The running maximum, or the lower envelope for editions starting after last_day.

    rows: scraped days, in date order within each tid.
    """
    held = rows.groupby('tid')['entry_count'].cummax()
    envelope = rows[::-1].groupby('tid')['entry_count'].cummin()[::-1]
    return held.where(rows['start'] <= last_day, envelope).astype(int)
