"""Registration curves built from the nightly scrape, for editions the export never saw.

The admin export stops at its snapshot (2026-03-21). 01_data_prep extends the
curves of events the export already held; an edition that opened after the
snapshot has only the scrape. Its curve is the scrape's gross entry count,
held to a running maximum, one row per scraped day, T in days before the
event start. Days after the start are left out, as the loader drops them
from export curves, and so are days with no entries, as 01_data_prep drops
them.
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
    rows = scrape[['tournament_name', 'date', 'entry_count']]
    rows = rows.assign(key=rows['tournament_name'].map(edition_key)).drop(columns='tournament_name')
    rows = rows.merge(editions, on='key')
    rows = rows.assign(date=pd.to_datetime(rows['date']).dt.normalize())
    rows['T'] = (rows['start'] - rows['date']).dt.days
    rows = rows[(rows['T'] >= 0) & (rows['entry_count'] > 0)]
    rows = rows.sort_values(['tid', 'T'], ascending=[True, False], kind='stable')
    rows = rows.drop_duplicates(['tid', 'T'], keep='last')
    rows['cum_regs'] = rows.groupby('tid')['entry_count'].cummax().astype(int)
    rows['daily_regs'] = rows.groupby('tid')['cum_regs'].diff().fillna(rows['cum_regs']).astype(int)
    rows['cum_pct'] = (rows['cum_regs'] / rows['final_count']).where(rows['final_count'] > 0)
    return rows[CURVE_COLUMNS].reset_index(drop=True)
