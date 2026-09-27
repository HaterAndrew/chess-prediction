"""Which events the walk-forward backtest grades."""
import pandas as pd

from corpus.calendar import event_calendar
from shared.side_events import SIDE_EVENT_PATTERN
from shared.thresholds import MIN_FINAL_COUNT
from tournament_aliases import is_wo_excluded

from perf.evaluation import is_curve_gradeable

# Graded apart from the site, which shows it: its history is the combined
# World Open, ten times its size.
WO_PERF_EXTRA = {'World Open lower sections', 'World Open, lower sections'}


def snapshot_date(summary):
    """When the registration export was taken: the latest registration it holds."""
    col = 'snapshot_last_reg' if 'snapshot_last_reg' in summary.columns else 'last_reg'
    return pd.to_datetime(summary[col], errors='coerce').max().normalize()


def scraped_names(scrape):
    """Editions the nightly scrape has counted entries for."""
    if scrape is None:
        return set()
    return set(scrape.loc[scrape['entry_count'] > 0, 'tournament_name'])


def _flag(frame, col):
    return frame[col].fillna(False).astype(bool)


def final_is_known(ev, today, snapshot, scraped):
    """Finished before today, with a final that can be trusted.

    The final is the export's when the event ended before the snapshot, and
    otherwise must be one the nightly scrape counted.
    """
    return ((ev['end'] < today)
            & ((ev['end'] < snapshot) | ev['tournament_name'].isin(scraped)))


def _eligible(ev, today, first_season, snapshot, scraped):
    """In person, a real field, dated, with a known final."""
    excluded = ev['family'].map(lambda f: is_wo_excluded(f) or f in WO_PERF_EXTRA)
    side = ev['family'].str.contains(SIDE_EVENT_PATTERN, case=False, na=False, regex=True)
    return (ev['tournament_year'].between(first_season, today.year)
            & _flag(ev, 'has_timestamps') & ~_flag(ev, 'is_online') & ~_flag(ev, 'is_covid')
            & ~side & ~excluded.astype(bool)
            & (ev['final_count'] >= MIN_FINAL_COUNT)
            & ev['start'].notna() & final_is_known(ev, today, snapshot, scraped))


def finished_events(corpus, today):
    """Every edition with a start date and a known final, with its start and end."""
    today = pd.Timestamp(today).normalize()
    ev = corpus.summary.merge(event_calendar(corpus.summary, corpus.meta), on='tid')
    known = final_is_known(ev, today, snapshot_date(corpus.summary), scraped_names(corpus.scrape))
    return ev[known & ev['start'].notna() & (ev['final_count'] > 0)].reset_index(drop=True)


def gradeable_events(corpus, today, first_season):
    """The editions the walk-forward grades, with their start and end."""
    today = pd.Timestamp(today).normalize()
    snapshot = snapshot_date(corpus.summary)
    ev = corpus.summary.merge(event_calendar(corpus.summary, corpus.meta), on='tid')
    ev = ev[_eligible(ev, today, first_season, snapshot, scraped_names(corpus.scrape))].copy()
    curves = dict(tuple(corpus.daily.groupby('tid')))
    empty = corpus.daily.iloc[0:0]
    ev = ev[[is_curve_gradeable(curves.get(tid, empty), final)[0]
             for tid, final in zip(ev['tid'], ev['final_count'])]]
    return ev.reset_index(drop=True)
