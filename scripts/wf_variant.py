"""Run the walk-forward on the code and data in this tree and write its records.

    python scripts/wf_variant.py --out /path/records.csv
    python scripts/wf_variant.py --out /path/cold.csv --cold-start finals

A challenger is a branch: build it into a scratch copy beside a copy of main,
run this in both, and compare the two files with scripts/perf_diff.py.
--cold-start forecasts every event as if no model had trained on its family
(perf.cold_start). Writes nothing but --out.
"""
import argparse
import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from corpus import load_corpus  # noqa: E402
from perf.cold_start import MODES  # noqa: E402
from perf.walkforward import run_walk_forward  # noqa: E402
from perf.wf_run import write_records  # noqa: E402
from shared.clock import today_ts  # noqa: E402
from shared.paths import OUTPUT_DIR  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', required=True)
    parser.add_argument('--cold-start', choices=MODES)
    parser.add_argument('--today', help='YYYY-MM-DD; default: today')
    args = parser.parse_args(argv)
    today = pd.Timestamp(args.today) if args.today else today_ts()
    started = time.monotonic()
    records, warnings = run_walk_forward(load_corpus(OUTPUT_DIR), today,
                                         cold_start=args.cold_start)
    for w in warnings:
        print(f"  walk-forward fit {w}")
    write_records(records, args.out)
    events = len({r['tid'] for r in records})
    print(f"{len(records)} forecasts of {events} events in {time.monotonic() - started:.0f} s "
          f"-> {args.out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
