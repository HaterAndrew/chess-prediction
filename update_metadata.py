"""
Early-bird feature integration: expand tournament_metadata.csv with
estimated early-bird deadlines from registration spike patterns.

Reads detected early_bird_spike data from 01_data_prep.py output and
cross-references against existing metadata to find families with spikes
but no metadata entry.

Usage:
  python update_metadata.py                  # analyze and generate expanded CSV
  python update_metadata.py --write          # overwrite metadata with expanded version
  python update_metadata.py --year 2026      # only estimate for a specific year
"""

import pandas as pd
import numpy as np
import os
import argparse

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
META_PATH = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")


def load_data():
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))
    meta = pd.read_csv(META_PATH)
    return summary, daily, meta


def estimate_early_bird_from_spikes(summary, daily):
    """
    For families with detected early-bird spikes, estimate the deadline
    as the spike_day (days before event) derived from the spike detection
    in 01_data_prep.py.

    Returns a DataFrame with family-level spike estimates.
    """
    # Get tournaments with detected spikes
    spiked = summary[
        (summary['early_bird_spike'] == True) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False)) &
        (summary['spike_day'].notna())
    ].copy()

    if spiked.empty:
        return pd.DataFrame(columns=['family', 'median_spike_day', 'n_spike_editions',
                                      'spike_day_range', 'estimated_eb_days_before'])

    # Aggregate spike patterns per family
    fam_spikes = spiked.groupby('family').agg(
        median_spike_day=('spike_day', 'median'),
        n_spike_editions=('spike_day', 'size'),
        min_spike_day=('spike_day', 'min'),
        max_spike_day=('spike_day', 'max'),
        mean_magnitude=('spike_magnitude', 'mean'),
    ).reset_index()

    fam_spikes['spike_day_range'] = fam_spikes.apply(
        lambda r: f"{int(r['min_spike_day'])}-{int(r['max_spike_day'])}", axis=1
    )
    # Estimated EB deadline = median spike day (days before event)
    # The spike typically occurs right around the early-bird deadline
    fam_spikes['estimated_eb_days_before'] = fam_spikes['median_spike_day'].round(0).astype(int)

    return fam_spikes


def generate_expanded_metadata(summary, daily, meta, year_filter=None):
    """Generate expanded metadata with estimated early-bird deadlines."""

    spike_estimates = estimate_early_bird_from_spikes(summary, daily)

    # Families already in metadata
    meta_families = set(meta['family'].unique())

    # Families with spikes but NOT in metadata
    if spike_estimates.empty:
        missing = pd.DataFrame()
    else:
        missing = spike_estimates[~spike_estimates['family'].isin(meta_families)]

    print(f"\n{'='*60}")
    print(f"EARLY-BIRD METADATA INTEGRATION")
    print(f"{'='*60}")
    print(f"  Families in metadata:           {len(meta_families)}")
    print(f"  Families with detected spikes:  {len(spike_estimates)}")
    print(f"  Spikes with existing metadata:  {len(spike_estimates) - len(missing)}")
    print(f"  Spikes WITHOUT metadata:        {len(missing)}")

    # Report families with spikes but no metadata
    if not missing.empty:
        print(f"\n── Families with detected spikes but no metadata ──")
        for _, r in missing.iterrows():
            print(f"    {r['family']:<40} spike ~T-{r['estimated_eb_days_before']}  "
                  f"({int(r['n_spike_editions'])} editions, "
                  f"range T-{r['spike_day_range']}, "
                  f"avg magnitude {r['mean_magnitude']:.1f}x)")

    # Report families already in metadata — compare spike vs recorded deadline
    in_meta = spike_estimates[spike_estimates['family'].isin(meta_families)]
    if not in_meta.empty:
        print(f"\n── Spike vs metadata comparison (families in metadata) ──")
        for _, r in in_meta.iterrows():
            fam = r['family']
            # Get earliest metadata entry for this family with EB deadline
            m_rows = meta[(meta['family'] == fam) & (meta['early_bird_deadline'].notna())]
            if not m_rows.empty:
                # Compute days between start_date and early_bird_deadline
                m_row = m_rows.iloc[0]
                try:
                    start = pd.to_datetime(m_row['start_date'])
                    eb = pd.to_datetime(m_row['early_bird_deadline'])
                    meta_days = (start - eb).days
                    print(f"    {fam:<35} spike=T-{r['estimated_eb_days_before']}  "
                          f"metadata=T-{meta_days}  "
                          f"delta={abs(r['estimated_eb_days_before'] - meta_days)} days")
                except Exception:
                    pass

    # ── Build expanded metadata ──────────────────────────────────────
    # For missing families, create estimated metadata rows
    new_rows = []
    for _, spike in missing.iterrows():
        fam = spike['family']
        eb_days = spike['estimated_eb_days_before']

        # Get historical event timing from summary
        fam_hist = summary[
            (summary['family'] == fam) &
            (~summary['is_online'].fillna(False)) &
            (~summary['is_covid'].fillna(False)) &
            (summary['last_reg'].notna())
        ]

        if fam_hist.empty:
            continue

        # Estimate typical event date (month/day) from historical last_reg
        hist_dates = pd.to_datetime(fam_hist['last_reg'], errors='coerce').dropna()
        if hist_dates.empty:
            continue

        avg_month = int(hist_dates.dt.month.median())
        avg_day = int(hist_dates.dt.day.median())

        # Generate rows for recent + upcoming years
        years_to_generate = [2025, 2026] if year_filter is None else [year_filter]
        for yr in years_to_generate:
            try:
                est_start = pd.Timestamp(yr, avg_month, avg_day)
                est_eb = est_start - pd.Timedelta(days=int(eb_days))
                est_end = est_start + pd.Timedelta(days=3)  # typical 3-4 day event

                new_rows.append({
                    'family': fam,
                    'year': yr,
                    'start_date': est_start.strftime('%Y-%m-%d'),
                    'end_date': est_end.strftime('%Y-%m-%d'),
                    'early_bird_deadline': est_eb.strftime('%Y-%m-%d'),
                    'early_bird_fee': np.nan,
                    'regular_fee': np.nan,
                    'onsite_fee': np.nan,
                    'venue_city': '',
                    'venue_state': '',
                })
            except ValueError:
                continue

    expanded = pd.concat([meta, pd.DataFrame(new_rows)], ignore_index=True)
    expanded = expanded.sort_values(['family', 'year']).reset_index(drop=True)

    print(f"\n── Result ──")
    print(f"  Original metadata rows:  {len(meta)}")
    print(f"  New estimated rows:      {len(new_rows)}")
    print(f"  Expanded total:          {len(expanded)}")

    return expanded, new_rows


def main():
    parser = argparse.ArgumentParser(description="Expand metadata with early-bird spike estimates")
    parser.add_argument('--write', action='store_true',
                        help='Overwrite tournament_metadata.csv with expanded version')
    parser.add_argument('--year', type=int, default=None,
                        help='Only generate estimates for a specific year')
    args = parser.parse_args()

    summary, daily, meta = load_data()
    expanded, new_rows = generate_expanded_metadata(summary, daily, meta, year_filter=args.year)

    if not new_rows:
        print("\n  No new rows to add. Metadata is up to date.")
        return

    # Save expanded version
    expanded_path = os.path.join(OUTPUT_DIR, "tournament_metadata_expanded.csv")
    expanded.to_csv(expanded_path, index=False)
    print(f"\n  Saved expanded metadata to {expanded_path}")

    if args.write:
        expanded.to_csv(META_PATH, index=False)
        print(f"  OVERWROTE {META_PATH} with expanded version.")
    else:
        print(f"  Run with --write to overwrite {META_PATH}")


if __name__ == "__main__":
    main()
