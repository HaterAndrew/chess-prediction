"""
Data gap analysis: identify tournaments missing timestamps and prioritize
data requests to CCA.

Reports:
  - Tournaments lacking registration timestamps
  - Families that would benefit most from more timestamped data
  - Prioritized list of specific tournaments to request timestamps for
  - Outputs a CSV suitable for sending to CCA as a data request

Usage:
  python data_gaps.py                # full report + CSV output
  python data_gaps.py --top 20       # limit output to top N priorities
"""

import pandas as pd
import numpy as np
import os
import argparse

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")


def load_data():
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    family_stats = pd.read_csv(os.path.join(OUTPUT_DIR, "family_stats.csv"))
    return summary, family_stats


def analyze_gaps(summary, family_stats, top_n=None):
    """Analyze timestamp coverage and identify high-impact gaps."""

    # Filter to real in-person tournaments
    valid = summary[
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ].copy()

    total = len(valid)
    with_ts = valid['has_timestamps'].sum()
    without_ts = total - with_ts

    print(f"\n{'='*60}")
    print(f"DATA GAP REPORT")
    print(f"{'='*60}")
    print(f"  Total in-person tournaments (excl. COVID/online):  {total}")
    print(f"  With timestamps:    {int(with_ts)} ({with_ts/total*100:.1f}%)")
    print(f"  Without timestamps: {int(without_ts)} ({without_ts/total*100:.1f}%)")

    # ── Per-family gap analysis ──────────────────────────────────────
    fam_gap = valid.groupby('family').agg(
        n_editions=('tid', 'size'),
        n_timestamped=('has_timestamps', 'sum'),
        n_missing_ts=('has_timestamps', lambda x: (~x).sum()),
        mean_count=('final_count', 'mean'),
        min_year=('tournament_year', 'min'),
        max_year=('tournament_year', 'max'),
    ).reset_index()

    fam_gap['ts_coverage_pct'] = (fam_gap['n_timestamped'] / fam_gap['n_editions'] * 100).round(1)

    # ── Families that would benefit most from more data ──────────────
    # Priority score: families with many editions but few timestamps,
    # weighted by tournament size (bigger events = higher impact)
    fam_gap['priority_score'] = (
        fam_gap['n_missing_ts'] *
        np.log1p(fam_gap['mean_count']) *
        (1 - fam_gap['n_timestamped'] / fam_gap['n_editions'])
    ).round(2)

    # Families with at least 1 timestamped edition (so model can use the data)
    # but fewer than 5 (where more data would meaningfully improve predictions)
    high_impact = fam_gap[
        (fam_gap['n_timestamped'] >= 1) &
        (fam_gap['n_timestamped'] < 5) &
        (fam_gap['n_editions'] >= 3)
    ].sort_values('priority_score', ascending=False)

    # Families with zero timestamps (CCA backfill candidates)
    no_ts = fam_gap[
        (fam_gap['n_timestamped'] == 0) &
        (fam_gap['n_editions'] >= 3)
    ].sort_values('mean_count', ascending=False)

    print(f"\n── Families needing CCA backfill (0 timestamps, 3+ editions) ──")
    print(f"  {len(no_ts)} families with zero timestamp coverage")
    if len(no_ts) > 0:
        display = no_ts.head(top_n) if top_n else no_ts
        for _, r in display.iterrows():
            print(f"    {r['family']:<40} {int(r['n_editions']):>3} editions  avg={int(r['mean_count']):>5}")

    print(f"\n── Families that benefit most from more timestamps ──")
    print(f"  (have some timestamps but <5, with 3+ total editions)")
    if len(high_impact) > 0:
        display = high_impact.head(top_n) if top_n else high_impact
        for _, r in display.iterrows():
            print(f"    {r['family']:<40} {int(r['n_timestamped'])}/{int(r['n_editions'])} timestamped  "
                  f"avg={int(r['mean_count']):>5}  score={r['priority_score']:.1f}")

    # ── Specific tournaments to request ──────────────────────────────
    # Prioritize: recent years first, larger families first, bigger events first
    missing = valid[~valid['has_timestamps']].copy()
    missing = missing.merge(
        fam_gap[['family', 'n_timestamped', 'n_editions', 'priority_score']],
        on='family', how='left'
    )

    # Score individual tournaments
    missing['request_priority'] = (
        # Recent years more valuable
        (missing['tournament_year'].fillna(2015) - 2010) * 2 +
        # Families with some but not enough timestamps
        missing['n_timestamped'].fillna(0).clip(0, 5) * 3 +
        # Bigger tournaments more impactful
        np.log1p(missing['final_count']) * 2 +
        # Family-level priority
        missing['priority_score'].fillna(0)
    ).round(2)

    missing = missing.sort_values('request_priority', ascending=False)

    print(f"\n── Top tournament-level requests (prioritized by impact) ──")
    cols = ['tournament_name', 'family', 'tournament_year', 'final_count']
    display = missing.head(top_n if top_n else 30)
    for _, r in display.iterrows():
        yr = int(r['tournament_year']) if pd.notna(r['tournament_year']) else '????'
        print(f"    {yr}  {r['family']:<35} n={int(r['final_count']):>5}  priority={r['request_priority']:.1f}")

    # ── Export CSV for CCA ────────────────────────────────────────────
    request_csv = missing[['tid', 'tournament_name', 'family', 'tournament_year',
                           'final_count', 'request_priority']].copy()
    request_csv = request_csv.rename(columns={
        'tournament_year': 'year',
        'final_count': 'registrations',
        'request_priority': 'priority'
    })
    request_csv = request_csv.sort_values('priority', ascending=False)

    out_path = os.path.join(OUTPUT_DIR, "cca_timestamp_request.csv")
    request_csv.to_csv(out_path, index=False)
    print(f"\n  Exported {len(request_csv)} tournament requests to {out_path}")

    # ── Summary stats ─────────────────────────────────────────────────
    print(f"\n── Summary ──")
    print(f"  Families with 0 timestamps:     {len(no_ts)}")
    print(f"  Families needing more data:      {len(high_impact)}")
    print(f"  Individual tournaments missing:  {len(missing)}")
    print(f"  Request CSV:                     {out_path}")

    return request_csv


def main():
    parser = argparse.ArgumentParser(description="Data gap analysis for CCA timestamp requests")
    parser.add_argument('--top', type=int, default=None,
                        help='Limit output to top N priorities')
    args = parser.parse_args()

    summary, family_stats = load_data()
    analyze_gaps(summary, family_stats, top_n=args.top)


if __name__ == "__main__":
    main()
