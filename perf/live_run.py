"""Read the forecast ledgers, grade the live record, and report it in the log."""
import os

import pandas as pd

from shared.paths import OUTPUT_DIR

from perf.evaluation_periods import evaluation_blocks, load_original_evaluation
from perf.live_record import last_run_per_day, match_forecasts, summarize_live
from perf.wf_events import finished_events
from pipeline.ledger import LEDGER_FIELDS

# The backfill (published before the ledger existed) and the nightly ledger.
LEDGER_FILES = ('forecast_ledger_backfill.csv', 'forecast_ledger.csv')


def read_ledgers(output_dir):
    """Both ledgers as one frame; missing files are named so the log says so."""
    paths = [os.path.join(output_dir, name) for name in LEDGER_FILES]
    missing = [p for p in paths if not os.path.exists(p)]
    frames = [pd.read_csv(p) for p in paths if p not in missing]
    return (pd.concat(frames, ignore_index=True) if frames else None), missing


def live_record_block(corpus, today, output_dir=OUTPUT_DIR):
    """Grade every published forecast with a known final; print and return the block."""
    ledger, missing = read_ledgers(output_dir)
    for path in missing:
        print(f"WARNING: live record: {os.path.basename(path)} is missing")
    if ledger is None:
        ledger = pd.DataFrame(columns=LEDGER_FIELDS)
    runs = last_run_per_day(ledger)
    events = finished_events(corpus, today)
    unavailable = []
    records = match_forecasts(runs, events, unavailable=unavailable)
    first = runs['as_of'].min().strftime('%Y-%m-%d') if not runs.empty else None
    last = runs['as_of'].max().strftime('%Y-%m-%d') if not runs.empty else None
    block = summarize_live(records, first, last)
    block['n_unavailable_forecasts'] = len(unavailable)
    block['evaluation_periods'] = evaluation_blocks(ledger, events, load_original_evaluation())
    # Preserve the original payload for consumers of the existing field.
    block['holdout'] = block['evaluation_periods'][0]['results']
    if block['n_invalid_ranges']:
        print(f"WARNING: live record: {block['n_invalid_ranges']} published forecast(s) "
              f"have a range that does not hold the point; not scored")
    print(f"  Live record: {block['n_records']} published forecasts of "
          f"{block.get('n_events', 0)} finished events")
    if unavailable:
        print(f"  Live record: {len(unavailable)} unavailable forecast(s) not scored; "
              "no older forecast substituted")
    sealed = block['holdout']
    print(f"  Sealed test (frozen {sealed['frozen_on']}): {sealed['n_records']} forecasts of "
          f"{sealed.get('n_events', 0)} finished events")
    for T, m in block.get('pooled', {}).items():
        print(f"  Live T-{T:>2}: MAE {m['mae_pct']:5.2f}%  median error "
              f"{m['median_error_pct']:+5.2f}%  coverage {m['coverage']:5.1f}%  (n={m['n']})")
    return block
