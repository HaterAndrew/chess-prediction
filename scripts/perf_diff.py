"""Compare two walk-forward record files, horizon by horizon, and judge the change.

    python scripts/perf_diff.py BEFORE.csv AFTER.csv --band short
    python scripts/perf_diff.py BEFORE.csv AFTER.csv --kind removal
    python scripts/perf_diff.py BEFORE.csv AFTER.csv --kind subset --subset thin_history
    python scripts/perf_diff.py BEFORE.csv AFTER.csv --kind no_worse --subset thin_history

Prints n, MAE %, ALE, LIS, coverage and median error for each file at each
horizon (pooled and per season with --by-season), then the judge() verdict
on the forecasts both files made. Exits 1 when the change is rejected.
"""
import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from perf.acceptance import BANDS, KINDS, SUBSETS, judge  # noqa: E402
from perf.log_scores import absolute_log_error, log_interval_score  # noqa: E402


def horizon_table(records, by_season=False):
    """One row per horizon (and season): the figures a reviewer compares."""
    df = records.assign(
        ape=(records['point'] - records['final']).abs() / records['final'] * 100,
        ale=absolute_log_error(records['final'], records['point']),
        lis=log_interval_score(records['final'], records['low'], records['high']))
    keys = ['season', 'T'] if by_season else ['T']
    out = df.groupby(keys).agg(n=('tid', 'size'), mae_pct=('ape', 'mean'), ale=('ale', 'mean'),
                               lis=('lis', 'mean'), coverage=('in_range', 'mean'),
                               median_log_error=('log_error', 'median'))
    out['coverage'] *= 100
    return out.sort_index(ascending=[True] * (len(keys) - 1) + [False]).round(4)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('before')
    parser.add_argument('after')
    parser.add_argument('--band', choices=sorted(BANDS), default='short')
    parser.add_argument('--kind', choices=sorted(KINDS), default='improvement')
    parser.add_argument('--subset', choices=sorted(SUBSETS))
    parser.add_argument('--by-season', action='store_true')
    args = parser.parse_args(argv)
    if args.kind == 'subset' and not args.subset:
        parser.error('--kind subset needs --subset')
    before, after = pd.read_csv(args.before), pd.read_csv(args.after)
    table = horizon_table(before, args.by_season).join(
        horizon_table(after, args.by_season), lsuffix='_before', rsuffix='_after')
    print(table.to_string())
    verdict = judge(after.to_dict('records'), before.to_dict('records'),
                    band=args.band, kind=args.kind, subset=args.subset)
    print(json.dumps(verdict, indent=1, default=str))
    return 0 if verdict['accept'] else 1


if __name__ == '__main__':
    sys.exit(main())
