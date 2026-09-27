"""The live record: the forecasts the site published, graded against the finals.

The walk-forward re-creates forecasts; this grades the ones visitors saw, from
the forecast ledger and its backfill. For each finished event and horizon T the
forecast is the one published on the day T days before the start, or, when no
run published that day, on the latest day up to MATCH_DAYS earlier, never a
later one. Within a day the last run counts. Every route is graded, since every
route reached the page.
"""
import numpy as np
import pandas as pd

from perf.grading import T_POINTS
from perf.wf_summary import horizon_metrics
from tournament_aliases import canonicalize_family

MATCH_DAYS = 3


def _key(family, year):
    return list(zip(family.map(canonicalize_family), year.astype(int)))


def last_run_per_day(ledger):
    """One published row per event and day: the day's last run."""
    rows = ledger[ledger['published'] == 1].copy()
    rows['key'] = _key(rows['family'], rows['year'])
    rows['as_of'] = pd.to_datetime(rows['as_of_date'])
    rows = rows.sort_values(['run_ts', 'origin'], kind='stable')
    return rows.drop_duplicates(['key', 'as_of'], keep='last')


def _record(ev, T, row):
    point, low, high, final = (float(row['point']), float(row['ci_lower']),
                               float(row['ci_upper']), int(ev['final_count']))
    return {'season': int(ev['tournament_year']), 'tid': ev['tid'], 'family': ev['family'],
            'T': T, 'forecast_date': (ev['start'] - pd.Timedelta(days=T)).strftime('%Y-%m-%d'),
            'as_of_date': row['as_of'].strftime('%Y-%m-%d'),
            'point': point, 'low': low, 'high': high, 'final': final,
            'log_error': float(np.log(point / final)), 'in_range': int(low <= final <= high),
            'route': row['route'], 'model_hash': row['model_hash']}


def match_forecasts(runs, events, horizons=T_POINTS):
    """The published forecast for each finished event at each horizon it has one."""
    by_key = dict(tuple(runs.groupby('key')))
    records = []
    for _, ev in events.iterrows():
        rows = by_key.get((canonicalize_family(ev['family']), int(ev['tournament_year'])))
        if rows is None:
            continue
        for T in horizons:
            d = ev['start'] - pd.Timedelta(days=T)
            seen = rows[(rows['as_of'] <= d) & (rows['as_of'] >= d - pd.Timedelta(days=MATCH_DAYS))]
            if not seen.empty:
                records.append(_record(ev, T, seen.loc[seen['as_of'].idxmax()]))
    return records


def valid_ranges(records):
    """The records a range can be scored on, and how many could not be."""
    ok = [r for r in records if 0 < r['low'] <= r['point'] <= r['high']]
    return ok, len(records) - len(ok)


def _by_T(frame):
    return {str(T): horizon_metrics(g)
            for T, g in frame.sort_values('T', ascending=False).groupby('T', sort=False)}


def _era(model_hash, g):
    return {'model_hash': model_hash, 'first': g['as_of_date'].min(), 'last': g['as_of_date'].max(),
            'n': int(len(g)), 'n_events': int(g['tid'].nunique()),
            'mae_pct': round(float(((g['point'] - g['final']).abs() / g['final']).mean() * 100), 2),
            'coverage': round(float(g['in_range'].mean() * 100), 1)}


def summarize_live(records, first_date, last_date):
    """Pooled and per-route metrics by horizon, and each model version's record."""
    graded, invalid = valid_ranges(records)
    block = {'protocol': {'source': 'forecast ledger and its backfill',
                          'match_days': MATCH_DAYS, 'first_date': first_date,
                          'last_date': last_date},
             'n_records': len(graded), 'n_invalid_ranges': invalid}
    if not graded:
        return block
    df = pd.DataFrame(graded)
    eras = [_era(h, g) for h, g in df.groupby('model_hash')]
    return {**block, 'n_events': int(df['tid'].nunique()), 'pooled': _by_T(df),
            'by_route': {route: _by_T(g) for route, g in df.groupby('route')},
            'eras': sorted(eras, key=lambda e: e['first'])}
