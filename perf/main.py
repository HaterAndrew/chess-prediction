"""04e orchestrator: load the corpus, run the walk-forward, build the report."""
import time

from shared.clock import today_ts

from perf.folds import prepare_folds
from perf.report import build_report
from perf.wf_run import walk_forward_block

# 04e runs under a 1,200 s step timeout (pipeline.runner); say so well before it.
SLOW_RUN_S = 900


def main():
    started = time.monotonic()
    corpus, summary = prepare_folds()
    records, walk_forward = walk_forward_block(corpus, today_ts())
    build_report(summary, records, walk_forward=walk_forward)
    elapsed = time.monotonic() - started
    if elapsed > SLOW_RUN_S:
        print(f"WARNING: 04e took {elapsed:.0f} s, past {SLOW_RUN_S} s of its 1,200 s timeout")


if __name__ == "__main__":
    main()
