"""Which events the walk-forward backtest and the live record grade."""
import pandas as pd

from corpus.calendar import event_calendar
from corpus.labels import FINAL, PROVISIONAL, final_labels, scrape_dates
from shared.curves import has_curve
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


def _flag(frame, col):
    return frame[col].fillna(False).astype(bool)


def labelled_events(corpus, today):
    """Every summary event with its start, end and final label (corpus.labels)."""
    today = pd.Timestamp(today).normalize()
    ev = corpus.summary.merge(event_calendar(corpus.summary, corpus.meta), on='tid')
    ev['label'] = final_labels(ev, today, snapshot_date(corpus.summary),
                               scrape_dates(corpus.scrape))
    return ev


def _eligible(ev, first_season, today):
    """In person, a real field, a curve, dated, with a final label."""
    excluded = ev['family'].map(lambda f: is_wo_excluded(f) or f in WO_PERF_EXTRA)
    side = ev['family'].str.contains(SIDE_EVENT_PATTERN, case=False, na=False, regex=True)
    return (ev['tournament_year'].between(first_season, today.year)
            & has_curve(ev) & ~_flag(ev, 'is_online') & ~_flag(ev, 'is_covid')
            & ~side & ~excluded.astype(bool)
            & (ev['final_count'] >= MIN_FINAL_COUNT)
            & ev['start'].notna() & (ev['label'] == FINAL))


def finished_events(corpus, today):
    """Every edition with a start date and a final label."""
    ev = labelled_events(corpus, today)
    return ev[(ev['label'] == FINAL) & ev['start'].notna()
              & (ev['final_count'] > 0)].reset_index(drop=True)


def provisional_names(corpus, today):
    """Finished editions whose close neither source saw, oldest first."""
    ev = labelled_events(corpus, today)
    return ev.loc[ev['label'] == PROVISIONAL].sort_values('end')['tournament_name'].tolist()


def gradeable_events(corpus, today, first_season):
    """The editions the walk-forward grades, with their start and end."""
    today = pd.Timestamp(today).normalize()
    ev = labelled_events(corpus, today)
    ev = ev[_eligible(ev, first_season, today)].copy()
    curves = dict(tuple(corpus.daily.groupby('tid')))
    empty = corpus.daily.iloc[0:0]
    gradeable = pd.Series([is_curve_gradeable(curves.get(tid, empty), final)[0]
                           for tid, final in zip(ev['tid'], ev['final_count'])],
                          index=ev.index, dtype=bool)
    ev = ev[gradeable]
    return ev.reset_index(drop=True)
