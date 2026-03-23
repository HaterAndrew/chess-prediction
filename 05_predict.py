"""
Phase 5: Prediction Tool (v3 — with N5v4_Final model)
Uses winning models from the blind testing gauntlet:
  - Mode A: M1_Naive (3-year rolling mean)
  - Mode B: N5v4_Final (historical ratio + expanding-window LOO-calibrated CI)

Usage:
  python 05_predict.py                              # Show 2026 Chicago Open nowcast
  python 05_predict.py --family "Chicago Open"      # Nowcast for specific family
  python 05_predict.py --mode-a "Chicago Open" 2027 # Pre-registration forecast
"""

import pandas as pd
import numpy as np
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
m03 = import_module("03_models")
m04c = import_module("04c_final_model")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
DATA_PATH = os.path.expanduser("~/Downloads/all_registrations.csv")


def load_all_data():
    """Load and prepare all data for prediction."""
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))
    return summary, daily


def mode_a_forecast(family, year, summary):
    """Pre-registration total count forecast using naive baseline."""
    model = m03.M1_NaiveBaseline()
    # Train on all non-COVID, non-online data
    train = summary[
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ]
    model.fit(train)
    pred, lower, upper = model.predict_count(family, year)

    # Get historical context
    hist = summary[
        (summary['family'] == family) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ].sort_values('tournament_year')

    print(f"\n{'='*60}")
    print(f"MODE A FORECAST: {family} {year}")
    print(f"{'='*60}")
    print(f"  Point estimate:  {pred}")
    print(f"  80% interval:    [{lower}, {upper}]")
    print(f"\n  Historical editions:")
    for _, row in hist.tail(5).iterrows():
        yr = int(row['tournament_year']) if pd.notna(row['tournament_year']) else '?'
        print(f"    {yr}: {row['final_count']}")
    print(f"  3-year mean: {hist.tail(3)['final_count'].mean():.0f}")


def mode_b_nowcast(family, summary, daily, raw_df=None):
    """
    Nowcast using historical ratio model.
    Auto-detects current registration count if the tournament is in-progress.
    """
    # Train on all available non-COVID, non-online, timestamped data
    train = summary[
        (summary['has_timestamps']) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ]

    model = m04c.N5v4_Final()
    model.fit(train, daily)

    # Find the current (in-progress) tournament for this family
    current = summary[
        (summary['family'] == family) &
        (summary['tournament_year'] == 2026) &
        (~summary['is_online'].fillna(False))
    ]

    if len(current) == 0:
        print(f"No 2026 {family} tournament found in data.")
        return

    row = current.iloc[0]
    tid = row['tid']
    current_count = row['final_count']  # Current registrations so far

    # Estimate days remaining — check metadata first, then fall back to historical
    meta_path = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
    event_date_str = None
    eb_deadline_str = None
    if os.path.exists(meta_path):
        meta = pd.read_csv(meta_path)
        match = meta[(meta['family'] == family) & (meta['year'] == 2026)]
        if len(match) > 0:
            event_date_str = match.iloc[0]['start_date']
            eb_deadline_str = match.iloc[0].get('early_bird_deadline', None)

    if event_date_str:
        est_event = pd.Timestamp(event_date_str)
        today = pd.Timestamp.now()
        days_remaining = max((est_event - today).days, 0)
    else:
        hist = summary[
            (summary['family'] == family) &
            (~summary['is_online'].fillna(False)) &
            (~summary['is_covid'].fillna(False)) &
            (summary['last_reg'].notna())
        ]
        hist_dates = pd.to_datetime(hist['last_reg'], errors='coerce').dropna()
        if len(hist_dates) > 0:
            avg_month = int(hist_dates.dt.month.median())
            avg_day = int(hist_dates.dt.day.median())
            est_event = pd.Timestamp(2026, avg_month, avg_day)
            today = pd.Timestamp.now()
            days_remaining = max((est_event - today).days, 0)
        else:
            days_remaining = 60

    # Get ratio features from historical data
    fam_ratios = model.ratios.get(family, model.ratios.get('__global__', {}))

    print(f"\n{'='*60}")
    print(f"NOWCAST: {row['tournament_name']}")
    print(f"{'='*60}")
    print(f"  Current registrations:  {current_count}")
    if event_date_str:
        print(f"  Event start date:       {event_date_str}")
    print(f"  Days to event:          {days_remaining}")
    if eb_deadline_str:
        print(f"  Early bird deadline:    {eb_deadline_str}")
    print(f"  Model:                  N5v4_Final (expanding-window LOO calibration)")

    # Predict
    pred, lower, upper = model.predict_nowcast(current_count, days_remaining, family)

    if pred is not None:
        print(f"\n  Point estimate:  {pred}")
        print(f"  80% interval:    [{lower}, {upper}]")
    else:
        print(f"\n  Insufficient data for prediction at T-{days_remaining}")

    # Show predictions at multiple lead times for planning
    print(f"\n  Projection at different lead times:")
    print(f"  {'Lead Time':<12} {'Predicted':<12} {'80% CI':<20}")
    print(f"  {'-'*44}")

    for T in [90, 60, 42, 28, 14, 7, 3, 1]:
        p, lo, hi = model.predict_nowcast(current_count, T, family)
        if p is not None:
            marker = " <-- current" if abs(T - days_remaining) <= 3 else ""
            print(f"  T-{T:<9} {p:<12} [{lo}, {hi}]{marker}")

    # Historical context
    hist_final = summary[
        (summary['family'] == family) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False)) &
        (summary['tournament_year'] >= 2022)
    ]
    if len(hist_final) > 0:
        print(f"\n  Historical finals (2022+):")
        for _, h in hist_final.sort_values('tournament_year').iterrows():
            yr = int(h['tournament_year']) if pd.notna(h['tournament_year']) else '?'
            print(f"    {yr}: {h['final_count']}")

    # Show ratio details
    if family in model.ratios:
        closest_T = min(fam_ratios.keys(), key=lambda t: isinstance(t, (int, float)) and abs(t - days_remaining) or 9999) if fam_ratios else None
        if closest_T and closest_T in fam_ratios:
            raw_ratios = fam_ratios[closest_T]
            # N5v4 stores tuples (ratio, year, tid); extract just the ratio values
            if raw_ratios and isinstance(raw_ratios[0], tuple):
                ratio_vals = [r[0] for r in raw_ratios]
            else:
                ratio_vals = raw_ratios
            print(f"\n  Historical ratios at T-{closest_T}:")
            print(f"    Ratios: {[round(r, 2) for r in sorted(ratio_vals)]}")
            print(f"    Median: {np.median(ratio_vals):.2f}")


def list_families(summary):
    """Show available tournament families."""
    fam = summary[
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ].groupby('family').agg(
        editions=('tid', 'size'),
        latest=('tournament_year', 'max'),
        avg_count=('final_count', 'mean'),
    ).sort_values('editions', ascending=False)

    print(f"\nTop 30 Tournament Families:")
    print(fam.head(30).round(0).to_string())


def main():
    parser = argparse.ArgumentParser(description="Chess Tournament Registration Predictor")
    parser.add_argument('--family', type=str, default='Chicago Open',
                       help='Tournament family name')
    parser.add_argument('--mode-a', nargs=2, metavar=('FAMILY', 'YEAR'),
                       help='Mode A: pre-registration forecast (family year)')
    parser.add_argument('--list', action='store_true',
                       help='List available tournament families')
    args = parser.parse_args()

    summary, daily = load_all_data()

    if args.list:
        list_families(summary)
        return

    if args.mode_a:
        family, year = args.mode_a[0], int(args.mode_a[1])
        mode_a_forecast(family, year, summary)
        return

    # Default: Mode B nowcast
    mode_b_nowcast(args.family, summary, daily)


if __name__ == "__main__":
    main()
