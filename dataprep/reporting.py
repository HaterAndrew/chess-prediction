"""CSV saves, data-quality warnings, and EDA plots (01_data_prep,
verbatim). PNG outputs stay.
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

from shared.paths import OUTPUT_DIR


def save_outputs(summary, daily_counts):
    summary_path = os.path.join(OUTPUT_DIR, "tournament_summary.csv")
    summary.to_csv(summary_path, index=False)
    print(f"\nSaved tournament summary to {summary_path}")

    # Save daily counts for use in later phases
    daily_path = os.path.join(OUTPUT_DIR, "daily_registration_counts.csv")
    daily_counts.to_csv(daily_path, index=False)
    print(f"Saved daily registration counts to {daily_path}")


def dq_check(summary, daily_counts):
    # When scrape_end << final_count for a historical edition, it's a signal that
    # either (a) the daily scraper stopped running before event day, (b) the
    # recorded event_start date is wrong (so the daily series got truncated at
    # the wrong T), or (c) the family has a real late-arriving registration tail
    # our pipeline doesn't capture. The Cleveland Open 2025 metadata date bug
    # manifested as ratios of ~0.31 across 4 years before the date fix; now
    # ratios sit around 0.85-0.95. Anything < 0.5 is worth flagging for human
    # review. Warnings only — emitted as "WARNING:" so auto_update.py harvests
    # them into output/audit_warnings.json.
    _dq_threshold = 0.5
    # Editions triaged by hand (issue #7): event date verified against the
    # canonical source (drift 0) and the coverage gap confirmed real — a
    # COVID-era edition whose ratio can never improve. Suppress the recurring
    # WARNING (auto_update harvests that prefix) but keep the line visible;
    # the guardrail still fires for any new edition that degrades.
    _known_low_coverage = {('Continental Open', 2021)}
    # scrape_end = peak cum_regs per tid in daily_counts; final = summary.final_count
    _scrape_peak = daily_counts.groupby('tid')['cum_regs'].max().reset_index()
    _scrape_peak = _scrape_peak.rename(columns={'cum_regs': 'scrape_peak'})
    _dq = summary[['tid', 'family', 'tournament_year', 'final_count',
                   'is_online', 'is_covid']].merge(
        _scrape_peak, on='tid', how='left'
    ).fillna({'scrape_peak': 0})
    _dq = _dq[(_dq['final_count'] > 0) & (_dq['scrape_peak'] > 0)]
    _dq['ratio'] = _dq['scrape_peak'] / _dq['final_count']
    _dq_flagged = _dq[_dq['ratio'] < _dq_threshold].sort_values('ratio')
    if len(_dq_flagged) > 0:
        print(f"\n  Data-quality: {len(_dq_flagged)} edition(s) with scrape coverage < {_dq_threshold:.0%}")
        for _, row in _dq_flagged.iterrows():
            # Covid/online-flagged editions are excluded from both ratio engines
            # (ratio_model.build_ratio_model, 04c fit filters) — say so, or the
            # warning implies training pollution that cannot occur.
            excluded = bool(pd.notna(row['is_covid']) and row['is_covid']) or \
                       bool(pd.notna(row['is_online']) and row['is_online'])
            suffix = (" (covid/online-flagged; excluded from model training)"
                      if excluded else "")
            detail = (f"{row['family']} {int(row['tournament_year'])}: "
                      f"scrape={int(row['scrape_peak'])}/final={int(row['final_count'])} "
                      f"(ratio={row['ratio']:.2f}){suffix}")
            if (row['family'], int(row['tournament_year'])) in _known_low_coverage:
                print(f"  known low coverage (allowlisted, issue #7) — {detail}")
            else:
                print(f"  WARNING: low scrape coverage — {detail}")
    else:
        print(f"\n  Data-quality: all editions have scrape coverage >= {_dq_threshold:.0%}")


def eda_chicago(summary, daily_counts):
    print("\n── Chicago Open Analysis ──")

    chicago_tids = summary[
        (summary['family'].str.contains('Chicago Open', case=False, na=False)) &
        (~summary['is_online']) &
        (summary['has_timestamps']) &
        (~summary['is_covid'])
    ]
    print(f"Chicago Open editions with timestamps (non-COVID): {len(chicago_tids)}")
    print(chicago_tids[['tournament_name', 'tournament_year', 'final_count', 'early_bird_spike']].to_string(index=False))

    # Plot cumulative curves
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    for _, row in chicago_tids.iterrows():
        tid = row['tid']
        year = row['tournament_year']
        final = row['final_count']

        curve = daily_counts[daily_counts['tid'] == tid].sort_values('T', ascending=False)
        if len(curve) > 0:
            ax1.plot(curve['T'], curve['cum_pct'], label=f"{int(year)} (n={final})", linewidth=2)
            ax2.plot(curve['T'], curve['cum_regs'], label=f"{int(year)} (n={final})", linewidth=2)

    ax1.set_xlabel('Days Before Event')
    ax1.set_ylabel('Cumulative % of Final Registrations')
    ax1.set_title('Chicago Open — Normalized Cumulative Curves')
    ax1.legend()
    ax1.invert_xaxis()
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(120, 0)

    ax2.set_xlabel('Days Before Event')
    ax2.set_ylabel('Cumulative Registrations')
    ax2.set_title('Chicago Open — Absolute Cumulative Curves')
    ax2.legend()
    ax2.invert_xaxis()
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(120, 0)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "chicago_open_curves.png"), dpi=150)
    print("\nSaved Chicago Open curves plot to output/chicago_open_curves.png")


def eda_family_stats(summary):
    family_counts = summary.groupby('family').agg(
        n_editions=('tid', 'size'),
        n_timestamped=('has_timestamps', 'sum'),
        mean_count=('final_count', 'mean'),
        min_year=('tournament_year', 'min'),
        max_year=('tournament_year', 'max'),
    ).sort_values('n_editions', ascending=False)

    print("\n── Top 20 Tournament Families by Edition Count ──")
    print(family_counts.head(20).to_string())

    family_counts.to_csv(os.path.join(OUTPUT_DIR, "family_stats.csv"))
    return family_counts


def eda_yearly(summary):
    yearly = summary[~summary['is_online']].groupby('tournament_year').agg(
        n_tournaments=('tid', 'size'),
        total_registrations=('final_count', 'sum'),
        mean_per_tournament=('final_count', 'mean'),
        median_per_tournament=('final_count', 'median'),
    ).reset_index()

    print("\n── Year-over-Year Summary (in-person only) ──")
    print(yearly.to_string(index=False))

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(yearly['tournament_year'], yearly['total_registrations'], alpha=0.6, label='Total Registrations')
    ax2 = ax.twinx()
    ax2.plot(yearly['tournament_year'], yearly['mean_per_tournament'], 'r-o', label='Mean per Tournament')
    ax.set_xlabel('Year')
    ax.set_ylabel('Total Registrations')
    ax2.set_ylabel('Mean per Tournament')
    ax.set_title('CCA Tournament Registration Trends')
    ax.legend(loc='upper left')
    ax2.legend(loc='upper right')
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "yearly_trends.png"), dpi=150)
    print("Saved yearly trends plot to output/yearly_trends.png")


def final_stats(summary, family_counts, n_spikes):
    print(f"\n{'='*60}")
    print("PHASE 1 COMPLETE")
    print(f"{'='*60}")
    print(f"Tournaments: {len(summary)}")
    print(f"  With timestamps: {summary['has_timestamps'].sum()}")
    print(f"  COVID-era: {summary['is_covid'].sum()}")
    print(f"  Online (ICC): {summary['is_online'].sum()}")
    print(f"  Early-bird spikes detected: {n_spikes}")
    print(f"Families: {summary['family'].nunique()}")
    print(f"  With 5+ editions: {(family_counts['n_editions'] >= 5).sum()}")
    print(f"  With 3+ timestamped: {(family_counts['n_timestamped'] >= 3).sum()}")
    print(f"Output files in: {OUTPUT_DIR}")
