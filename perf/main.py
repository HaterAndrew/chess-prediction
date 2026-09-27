"""04e orchestrator: prepare folds, run year folds, run the walk-forward, build the report."""
import time

from shared.clock import today_ts

from perf.folds import prepare_folds, run_year_folds
from perf.report import build_report
from perf.wf_run import walk_forward_block

# 04e runs under a 1,200 s step timeout (pipeline.runner); say so well before it.
SLOW_RUN_S = 900


def main():
    started = time.monotonic()
    corpus, (summary, daily, meta, enrichment_lookup, completed_2026_tids) = prepare_folds()
    year_results, all_tournament_results = run_year_folds(
        summary, daily, meta, enrichment_lookup, completed_2026_tids)
    walk_forward = walk_forward_block(corpus, today_ts())
    build_report(summary, year_results, all_tournament_results, walk_forward=walk_forward)
    elapsed = time.monotonic() - started
    if elapsed > SLOW_RUN_S:
        print(f"WARNING: 04e took {elapsed:.0f} s, past {SLOW_RUN_S} s of its 1,200 s timeout")


if __name__ == "__main__":
    main()
