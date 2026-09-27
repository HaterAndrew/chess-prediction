"""The walk-forward records rebuilt into the views the Performance page reads."""
import numpy as np
import pandas as pd

from perf.wf_views import INTERVAL_FIELDS, season_views, tournament_results

HORIZONS = (14, 7, 3)


def _records():
    """Two seasons, six families, three horizons; one final below its range."""
    rows = []
    for season in (2025, 2026):
        for fam in range(6):
            final = 100 + 20 * fam
            start = pd.Timestamp(f'{season}-05-01') + pd.Timedelta(days=7 * fam)
            for T in HORIZONS:
                point = final + (5 if T > 3 else 2) + fam
                low, high = point - 20, point + 20
                if fam == 0 and T == 14:
                    low = final + 1
                rows.append({
                    'season': season, 'tid': season * 10 + fam, 'family': f'F{fam}', 'T': T,
                    'forecast_date': (start - pd.Timedelta(days=T)).strftime('%Y-%m-%d'),
                    'count': final // 2, 'point': point, 'low': low, 'high': high,
                    'final': final, 'log_error': float(np.log(point / final)),
                    'in_range': int(low <= final <= high),
                    'last_year': final - 10, 'pickup': None if fam == 5 else final + 3})
    return rows


def test_records_group_into_events_dated_by_their_start():
    results = tournament_results(_records())
    assert len(results) == 12
    first = results[0]
    assert (first['family'], first['event_start']) == ('F0', '2025-05-01')
    assert sorted(first['predictions']) == [3, 7, 14]
    p = first['predictions'][14]
    assert (p['predicted'], p['ci_lower'], p['in_ci']) == (105, 101, 0)
    assert p['error_pct'] == 5.0 and p['abs_error_pct'] == 5.0
    assert p['baseline_last_year'] == 90 and p['baseline_pickup'] == 103


def test_each_season_and_the_pool_carry_the_interval_figures():
    years, pooled = season_views(_records())
    assert sorted(years) == [2025, 2026]
    assert pooled['n_tournaments'] == 12 and pooled['seasons'] == [2025, 2026]
    assert years[2026]['n_tournaments'] == 6 and years[2026]['year'] == 2026
    row = next(a for a in pooled['aggregate'] if a['T'] == 14)
    assert set(INTERVAL_FIELDS) <= set(row)
    assert row['n'] == 12 and row['below_pct'] == round(2 / 12 * 100, 1)
    lo, hi = row['coverage_ci']
    assert lo < row['ci_coverage'] < hi
    assert set(row['baselines']) == {'baseline_last_year', 'baseline_pickup'}
    assert row['baselines']['baseline_pickup']['n'] == 10


def test_the_published_pits_bin_to_the_published_histogram():
    _, pooled = season_views(_records())
    for row in pooled['aggregate']:
        pits = [p['pit'] for t in pooled['tournaments'] for p in t['predictions']
                if p['T'] == row['T'] and 'pit' in p]
        counts = np.histogram(np.clip(pits, 0, 1), bins=row['pit']['bins'], range=(0, 1))[0]
        assert counts.tolist() == row['pit']['counts']


def test_no_records_gives_an_empty_pool():
    years, pooled = season_views([])
    assert years == {} and pooled['n_tournaments'] == 0 and pooled['grade'] == 'N/A'
