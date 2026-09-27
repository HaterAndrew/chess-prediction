"""Walk-forward backtest: every forecast made the way production would have made it then.

A forecast T days out is dated d = start - T. The models are refit on the
first of each month from the corpus as it stood that day and serve every
forecast dated that month. The event's count comes from curve rows dated by
d, its history from editions finished by the refit, and the forecast goes
through forecast_event like a published one. Nothing it reads was known
after d.
"""
import contextlib
import io
import math
from dataclasses import dataclass

import pandas as pd

from corpus.calendar import event_calendar
from corpus.coverage import count_as_of
from forecast import Event, Observation, fit_models, forecast_event
from model.data_io import build_enrichment_lookup
from sitebuild.editions import prior_editions
from sitebuild.helpers import _apply_wo_top6_adjustment, sanitize_early_bird
from tournament_aliases import FAMILY_ALIASES

from perf.grading import T_POINTS
from perf.schedule import FIRST_SEASON, forecast_points, monthly_cutoffs
from perf.wf_baselines import last_year_point, pickup_point
from perf.wf_events import gradeable_events, snapshot_date


def _quietly(fn, *args, **kwargs):
    """Run fn with its output captured; return its result and the WARNING lines."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = fn(*args, **kwargs)
    return out, [line.strip() for line in buf.getvalue().splitlines() if 'WARNING' in line]


def completed_in(view, season):
    """This season's in-person events finished by the view's date: the rolling retrain set."""
    s = view.summary
    done = ((s['tournament_year'] == season) & s['final_count'].notna()
            & s['has_timestamps'].fillna(False).astype(bool)
            & ~s['is_online'].fillna(False).astype(bool))
    return set(s.loc[done, 'tid'])


def fit_as_of(view, season):
    """fit_models on a view, as the nightly would have run it that day."""
    return _quietly(fit_models, view.summary, view.daily,
                    build_enrichment_lookup(view.enrichment), completed_in(view, season),
                    season=season, standings=view.standings, verbose=False)


@dataclass(frozen=True)
class _Curves:
    """Every event's curve, and the horizon through which its export is exact."""
    by_tid: dict
    bounds: dict
    empty: pd.DataFrame

    def curve(self, tid):
        return self.by_tid.get(tid, self.empty)

    def bound(self, tid):
        return self.bounds.get(tid)


def curves_of(corpus):
    """Curves by event; an event still running at the export snapshot is exact only up to it."""
    snapshot = snapshot_date(corpus.summary)
    cal = event_calendar(corpus.summary, corpus.meta)
    bounds = {tid: int((start - snapshot).days)
              for tid, start, end in zip(cal['tid'], cal['start'], cal['end'])
              if pd.notna(start) and not end < snapshot}
    return _Curves(dict(tuple(corpus.daily.groupby('tid'))), bounds, corpus.daily.iloc[0:0])


def prior_as_of(view, family, year):
    """The family's finished editions before `year`, oldest first, as the card finds them."""
    families = [family] + FAMILY_ALIASES.get(family, [])
    hist = prior_editions(view.summary, families, year, lambda fam, yr: True)
    return hist[hist['final_count'].notna()]


def history_counts(family, prior):
    """Their finals as the card lists them (pre-split World Open scaled to its top six)."""
    return [h['count'] for h in _apply_wo_top6_adjustment(family, [
        {'year': int(r['tournament_year']), 'count': int(r['final_count']), 'family': r['family']}
        for _, r in prior.iterrows()])]


def early_bird(meta, family, year, start):
    """The event's early-bird deadline, when it is a real one (the card's rule)."""
    m = meta[(meta['family'] == family) & (meta['year'] == year)]
    if m.empty:
        return None
    row = m.iloc[0]

    def value(col):
        return row[col] if col in row.index and pd.notna(row[col]) else None
    fee, reg = value('early_bird_fee'), value('regular_fee')
    deadline, _ = sanitize_early_bird(family, year, value('early_bird_deadline'),
                                      float(fee) if fee is not None else None,
                                      float(reg) if reg is not None else None,
                                      start.strftime('%Y-%m-%d'))
    return deadline


def forecast_record(ev, T, d, cutoff, view, fitted, eb_deadline, curves):
    """One graded forecast with its baselines, or None when there was no count or forecast."""
    seen = count_as_of(curves.curve(ev['tid']), T, exact_until_T=curves.bound(ev['tid']))
    if not seen.count:
        return None
    family, year = ev['family'], int(ev['tournament_year'])
    prior = prior_as_of(view, family, year)
    history = history_counts(family, prior)
    f = forecast_event(Event(family, event_start=ev['start'], early_bird_deadline=eb_deadline),
                       Observation(seen.count, T), fitted, history, as_of=d)
    if f is None:
        return None
    final = int(ev['final_count'])
    return {'season': year, 'tid': ev['tid'], 'family': family, 'T': T,
            'forecast_date': d.strftime('%Y-%m-%d'), 'cutoff': cutoff.strftime('%Y-%m-%d'),
            'count': seen.count, 'count_basis': seen.basis,
            'point': int(f.point), 'low': int(f.low), 'high': int(f.high),
            'raw_point': int(round(f.raw_point)), 'final': final,
            'log_error': round(math.log(f.point / final), 6),
            'in_range': int(f.low <= final <= f.high),
            'route': f.route, 'tier': f.tier,
            'last_year': last_year_point(history),
            'pickup': pickup_point(seen.count, T, prior, curves.curve, curves.bound)}


def run_walk_forward(corpus, today, first_season=FIRST_SEASON, horizons=T_POINTS):
    """Every graded forecast, in forecast-date order, and the warnings the fits raised."""
    events = gradeable_events(corpus, today, first_season).set_index('tid', drop=False)
    cutoffs = monthly_cutoffs(first_season, today)
    by_cutoff = {}
    for point in forecast_points(events, horizons, cutoffs, today):
        by_cutoff.setdefault(point[3], []).append(point)
    curves = curves_of(corpus)
    eb = {tid: _quietly(early_bird, corpus.meta, ev['family'], int(ev['tournament_year']),
                        ev['start'])[0] for tid, ev in events.iterrows()}
    records, warnings = [], []
    for cutoff in sorted(by_cutoff):
        view = corpus.as_of(cutoff)
        fitted, warned = fit_as_of(view, cutoff.year)
        warnings += [f"{cutoff.date()}: {w}" for w in warned]
        for tid, T, d, _ in by_cutoff[cutoff]:
            rec = forecast_record(events.loc[tid], T, d, cutoff, view, fitted, eb[tid], curves)
            if rec is not None:
                records.append(rec)
    records.sort(key=lambda r: (r['forecast_date'], r['tid'], -r['T']))
    return records, warnings
