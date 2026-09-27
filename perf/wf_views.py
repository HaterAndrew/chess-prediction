"""The walk-forward records in the shape the Performance page reads.

One view per season and one pooled across seasons, each with the events it
graded (a prediction per horizon), the aggregate row per horizon the page has
always drawn, a letter grade, and beside each aggregate row the walk-forward's
interval figures: coverage and median error with their 95% intervals, the tail
shares, and the proper scores with their family-block standard errors.
"""
import pandas as pd

from perf.evaluation import format_results
from perf.grading import compute_aggregate, grade_from_aggregate
from perf.scoring import record_pit
from perf.wf_summary import horizon_metrics

# The interval figures each aggregate row carries from the walk-forward summary.
INTERVAL_FIELDS = ('median_error_pct', 'median_error_ci', 'coverage_ci',
                   'below_pct', 'above_pct', 'ale', 'lis')


def _whole(value):
    return None if value is None or pd.isna(value) else int(value)


def prediction(rec):
    """One record as the page's prediction cell."""
    final, point, low, high = rec['final'], rec['point'], rec['low'], rec['high']
    error_pct = round((point - final) / final * 100, 1)
    pred = {'T': rec['T'], 'count_at_T': rec['count'], 'predicted': point,
            'ci_lower': low, 'ci_upper': high, 'error_pct': error_pct,
            'abs_error_pct': abs(error_pct), 'in_ci': rec['in_range'],
            'baseline_last_year': _whole(rec.get('last_year')),
            'baseline_pickup': _whole(rec.get('pickup'))}
    pit = record_pit(final, point, low, high)
    if pit is not None:
        pred['pit'] = pit
    return pred


def tournament_results(records):
    """The records grouped by event: family, final, start date, predictions keyed by horizon."""
    events = {}
    for rec in records:
        start = pd.Timestamp(rec['forecast_date']) + pd.Timedelta(days=int(rec['T']))
        ev = events.setdefault(rec['tid'], {
            'family': rec['family'], 'final_count': int(rec['final']),
            'event_start': start.strftime('%Y-%m-%d'), 'predictions': {}})
        ev['predictions'][int(rec['T'])] = prediction(rec)
    return sorted(events.values(), key=lambda e: (e['event_start'], e['family']))


def _with_intervals(aggregate, frame):
    by_T = {T: horizon_metrics(g) for T, g in frame.groupby('T')}
    for row in aggregate:
        m = by_T[row['T']]
        row.update({k: m[k] for k in INTERVAL_FIELDS})
    return aggregate


def view(records):
    """One view: n, grade, aggregate rows with their intervals, and the events."""
    results = tournament_results(records)
    aggregate = _with_intervals(compute_aggregate(results), pd.DataFrame(records))
    grade, detail = grade_from_aggregate(aggregate)
    return {'n_tournaments': len(results), 'grade': grade, 'grade_detail': detail,
            'aggregate': aggregate, 'tournaments': format_results(results)}


def season_views(records):
    """{season: view} for every season with a graded forecast, and the pooled view."""
    seasons = sorted({int(r['season']) for r in records})
    years = {s: {'year': s, **view([r for r in records if int(r['season']) == s])}
             for s in seasons}
    pooled = view(records) if records else {'n_tournaments': 0, 'grade': 'N/A',
                                            'grade_detail': 'No data', 'aggregate': [],
                                            'tournaments': []}
    if seasons:
        pooled['seasons'] = [seasons[0], seasons[-1]]
    return years, pooled
