"""The corpus as it stood on a date.

A backtest forecast made on date d may read only what was known on d.
Corpus holds every source the models read; Corpus.as_of(d) hides what came
later: the outcome fields of events not finished by d, curve rows dated after
d, the standings and enrichment of events not finished by d, and scrape rows
after d. An event counts as finished once its last day is before d, the rule
the site uses. The schedule (metadata) is published ahead, so it stays whole.
"""
from dataclasses import dataclass, replace
from typing import Optional

import pandas as pd

from tournament_aliases import STANDINGS_NAME_MAP

from corpus.calendar import event_calendar, meta_dates

# Summary fields that describe how an event turned out.
OUTCOME_COLUMNS = ('final_count', 'ts_count', 'last_reg', 'snapshot_last_reg',
                   'early_bird_spike', 'spike_day', 'spike_magnitude',
                   'active_count', 'withdrawal_count')


@dataclass(frozen=True)
class Corpus:
    summary: pd.DataFrame
    # Registration curves, T in days before the event start.
    daily: pd.DataFrame
    meta: pd.DataFrame
    standings: Optional[pd.DataFrame] = None
    enrichment: Optional[pd.DataFrame] = None
    scrape: Optional[pd.DataFrame] = None
    # None for the corpus as loaded; the date of a view.
    as_of_date: Optional[pd.Timestamp] = None

    def as_of(self, d):
        return corpus_as_of(self, d)


def corpus_as_of(corpus, d):
    """The corpus with everything after date d hidden."""
    d = pd.Timestamp(d).normalize()
    if corpus.as_of_date is not None and d > corpus.as_of_date:
        raise ValueError(f"a view as of {corpus.as_of_date.date()} cannot see {d.date()}")
    cal = event_calendar(corpus.summary, corpus.meta)
    finished = set(cal.loc[cal['end'] < d, 'tid'])
    return replace(corpus,
                   summary=_summary_as_of(corpus.summary, finished, d),
                   daily=_curves_as_of(corpus.daily, cal, finished, d),
                   standings=_standings_as_of(corpus.standings, corpus.meta, d),
                   enrichment=_enrichment_as_of(corpus.enrichment, d),
                   scrape=_scrape_as_of(corpus.scrape, d),
                   as_of_date=d)


def _summary_as_of(summary, finished, d):
    out = summary.copy()
    pending = ~out['tid'].isin(finished)
    for col in OUTCOME_COLUMNS:
        if col in out.columns:
            out[col] = out[col].where(~pending)
    if 'first_reg' in out.columns:
        opened = pd.to_datetime(out['first_reg'], errors='coerce').dt.normalize()
        out['first_reg'] = out['first_reg'].where(~(opened > d))
    return out


def _curves_as_of(daily, cal, finished, d):
    """Finished events keep their curves; the rest keep rows dated by d.

    An unfinished event with no known start cannot be placed in time, so its
    curve goes. Its cum_pct, a share of the final count, is not known yet.
    """
    days_out = dict(zip(cal['tid'], (cal['start'] - d).dt.days))
    cut_T = daily['tid'].map(days_out)
    done = daily['tid'].isin(finished)
    out = daily[done | (cut_T.notna() & (daily['T'] >= cut_T))].copy()
    if 'cum_pct' in out.columns:
        out['cum_pct'] = out['cum_pct'].where(out['tid'].isin(finished))
    return out


def _standings_as_of(standings, meta, d):
    """Past seasons' standings, and this season's for events finished by d.

    A standings row whose name does not resolve to a metadata event goes
    until its season is over.
    """
    if standings is None or standings.empty:
        return standings
    ends = {key: end for key, (_, end) in meta_dates(meta).items()}
    families = standings['tournament_name'].map(lambda n: STANDINGS_NAME_MAP.get(n, n))
    end = pd.Series([ends.get((fam, int(yr)), pd.NaT) if pd.notna(yr) else pd.NaT
                     for fam, yr in zip(families, standings['year'])],
                    index=standings.index, dtype='datetime64[ns]')
    return standings[(standings['year'] < d.year) | (end < d)].copy()


def _enrichment_as_of(enrichment, d):
    if enrichment is None or enrichment.empty:
        return enrichment
    end = pd.to_datetime(enrichment['end_date'], errors='coerce')
    known = (end < d) | (end.isna() & (enrichment['year'] < d.year))
    return enrichment[known].copy()


def _scrape_as_of(scrape, d):
    if scrape is None:
        return None
    return scrape[pd.to_datetime(scrape['date']) <= d].copy()
