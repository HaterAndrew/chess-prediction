"""Run the walk-forward backtest, archive its records, and report it in the log."""
import os
import time

import pandas as pd

from corpus.edition_counts import snapshot_date
from shared.paths import OUTPUT_DIR

from perf.route_evidence import STAND_IN, route_evidence
from perf.schedule import FIRST_SEASON, monthly_cutoffs
from perf.walkforward import run_walk_forward
from perf.wf_events import provisional_names
from perf.wf_summary import summarize

RECORDS_CSV = "walk_forward_records.csv"
RECORD_COLUMNS = ['season', 'tid', 'family', 'T', 'forecast_date', 'cutoff', 'count',
                  'count_basis', 'point', 'low', 'high', 'raw_point', 'final',
                  'log_error', 'in_range', 'route', 'tier', 'last_year', 'pickup',
                  'n_history', 'pace_point', 'pace_low', 'pace_high',
                  'hist_point', 'hist_low', 'hist_high']


def write_records(records, path):
    """Every graded forecast with its log error: the archive calibration fits on."""
    pd.DataFrame(records, columns=RECORD_COLUMNS).to_csv(path, index=False)


def walk_forward_block(corpus, today, output_dir=OUTPUT_DIR):
    """Run the walk-forward, write its records, print its summary; return the records and block."""
    started = time.monotonic()
    records, warnings = run_walk_forward(corpus, today)
    for w in warnings:
        print(f"  walk-forward fit {w}")
    write_records(records, os.path.join(output_dir, RECORDS_CSV))
    n_cutoffs = len(monthly_cutoffs(FIRST_SEASON, today))
    block = summarize(records, FIRST_SEASON, n_cutoffs, snapshot_date(corpus.summary))
    block['route_evidence'] = route_evidence(records)
    wins = [r for r in block['route_evidence'] if r['verdict'] == STAND_IN]
    print(f"  Route evidence: {len(block['route_evidence'])} bucket comparisons, "
          f"{len(wins)} won by a stand-in route")
    for r in wins:
        print(f"    {r['route']} beats the model: {r['band']} horizons, count {r['count_band']}, "
              f"history {r['history']} (LIS {r['lis_diff']:+.3f} +/- {r['lis_diff_se']:.3f}, n={r['n']})")
    # Finished, but neither the export nor the scrape saw registration close.
    block['provisional'] = provisional_names(corpus, today)
    if block['provisional']:
        print(f"  Not graded, final unconfirmed ({len(block['provisional'])}): "
              f"{', '.join(block['provisional'])}")
    print(f"  Walk-forward: {block['n_records']} forecasts of {block.get('n_events', 0)} "
          f"events from {FIRST_SEASON}, {n_cutoffs} monthly refits, "
          f"{time.monotonic() - started:.0f} s")
    for T, m in block.get('pooled', {}).items():
        print(f"  Walk-forward T-{T:>2}: MAE {m['mae_pct']:5.2f}%  median error "
              f"{m['median_error_pct']:+5.2f}%  coverage {m['coverage']:5.1f}%  (n={m['n']})")
    return records, block
