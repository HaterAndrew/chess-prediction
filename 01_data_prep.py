"""
Phase 1: Data Prep & EDA
- Parse all_registrations.csv
- Extract tournament families
- Build tournament summary table
- Compute days-before-event for timestamped registrations
- Detect early-bird spikes
- Visualize Chicago Open cumulative curves
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import re
import os

# ── Config ──────────────────────────────────────────────────────────────────
DATA_PATH = os.path.expanduser("~/Downloads/all_registrations.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Load Data ───────────────────────────────────────────────────────────────
print("Loading data...")
df = pd.read_csv(DATA_PATH)
print(f"  {len(df):,} registrations, {df['tid'].nunique()} tournaments")

# Parse timestamps
df['registered_time'] = pd.to_datetime(df['registered_time'], errors='coerce')
# Null out the 0000-00-00 sentinel values (they become NaT from errors='coerce')
null_mask = df['registered_time'].isna() | (df['registered_time'].dt.year < 2000)
df.loc[null_mask, 'registered_time'] = pd.NaT

has_ts = df['registered_time'].notna()
print(f"  {has_ts.sum():,} registrations with valid timestamps")

# ── Extract Tournament Family ───────────────────────────────────────────────
def extract_family(name):
    """Strip leading year and normalize tournament family name."""
    # Remove leading year (4 digits at start)
    cleaned = re.sub(r'^\d{4}\s+', '', name)
    # Remove "on ICC" suffix (COVID-era online variants)
    cleaned = re.sub(r'\s+on ICC$', '', cleaned, flags=re.IGNORECASE)
    # Normalize "CCA " prefix removal if it appears after year strip
    cleaned = re.sub(r'^CCA\s+', '', cleaned)
    # Strip whitespace
    cleaned = cleaned.strip()
    return cleaned


def canonicalize_family(name):
    """Fix known typos and normalize spacing/punctuation in family names."""
    # Fix common typos
    name = name.replace('Championshps', 'Championships')
    name = name.replace('Championsips', 'Championships')
    name = name.replace('Cahmpionships', 'Championships')
    # AUDIT.md C6 — fix Washington Chess Congress typo merging two families
    name = name.replace('Chess Congess', 'Chess Congress')
    # Normalize whitespace: collapse multiple spaces to one
    name = re.sub(r'\s{2,}', ' ', name)
    # Normalize apostrophes
    name = name.replace('\u2019', "'").replace('\u2018', "'")
    # Normalize World Open Under 13 name variants
    if re.match(r'^World Open Under 13\b', name):
        name = 'World Open Under 13'
    # Keep "World Open top 6 sections" and "World Open lower sections" as
    # separate families (no longer consolidated into "World Open").
    # All other World Open sub-events (G/7, G/10, Blitz, Action, Women,
    # Senior, Junior, etc.) are excluded downstream.
    # Normalize Women's Championship variants
    if name == "World Open Women s Championship":
        name = "World Open Womens Championship"
    # Normalize G7/G 7 variants
    if name == "World Open G 7 Championship":
        name = "World Open G7 Championship"
    # Atlantic City Open (2026+) is a NEW tournament, NOT a rename of Atlantic Open.
    # It uses Foxwoods/Princeton as comparable family (similar size, NE open format).
    # Leave as "Atlantic City Open" — model will use FAMILY_ALIASES for ratio lookup.
    # Remove trailing whitespace
    name = name.strip()
    return name


# Known administrative entries that are not real tournaments
ADMIN_ENTRIES = {
    'Send info to CCA', 'Send payment to CCA', 'Receiving prizes electronically',
    'Prize payment', 'Send info', 'Send payment',
}


df['family'] = df['tournament_name'].apply(extract_family).apply(canonicalize_family)

# Filter out administrative entries
admin_mask = df['family'].isin(ADMIN_ENTRIES)
if admin_mask.any():
    print(f"  Filtered {admin_mask.sum()} registrations from {df[admin_mask]['family'].nunique()} admin entries")
    df = df[~admin_mask].copy()

# Extract year from tournament name
def extract_year(name):
    m = re.match(r'^(\d{4})\s+', name)
    return int(m.group(1)) if m else None

df['tournament_year'] = df['tournament_name'].apply(extract_year)

# ── Build Tournament Summary ────────────────────────────────────────────────
print("\nBuilding tournament summary...")

summary = df.groupby('tid').agg(
    tournament_name=('tournament_name', 'first'),
    family=('family', 'first'),
    tournament_year=('tournament_year', 'first'),
    final_count=('tid', 'size'),
    has_timestamps=('registered_time', lambda x: x.notna().any()),
    ts_count=('registered_time', lambda x: x.notna().sum()),
    first_reg=('registered_time', 'min'),
    last_reg=('registered_time', 'max'),
).reset_index()

# COVID flag
summary['is_covid'] = summary['tournament_year'].isin([2020, 2021])

# Online flag (was "on ICC" in original name)
summary['is_online'] = summary['tournament_name'].str.contains('on ICC', case=False, na=False)

# ── Consolidate split sub-events ──────────────────────────────────────────
# Some tournaments (e.g., World Open) were split into multiple TIDs (top 6 /
# lower sections) starting in 2023 but represent one logical event. After
# family canonicalization, these share the same family+year. Merge them by
# summing counts and keeping the first TID as representative.
dup_mask = summary.duplicated(subset=['family', 'tournament_year'], keep=False)
if dup_mask.any():
    dups = summary[dup_mask].groupby(['family', 'tournament_year'])
    merge_map = {}  # old_tid -> keep_tid
    rows_to_drop = []
    for (fam, yr), group in dups:
        if len(group) <= 1:
            continue
        # Keep the TID with the most registrations as the representative
        keep_idx = group['final_count'].idxmax()
        keep_tid = group.loc[keep_idx, 'tid']
        combined_count = group['final_count'].sum()
        combined_ts_count = group['ts_count'].sum()
        has_ts = group['has_timestamps'].any()
        first_reg = group['first_reg'].min()
        last_reg = group['last_reg'].max()

        summary.loc[keep_idx, 'final_count'] = combined_count
        summary.loc[keep_idx, 'ts_count'] = combined_ts_count
        summary.loc[keep_idx, 'has_timestamps'] = has_ts
        summary.loc[keep_idx, 'first_reg'] = first_reg
        summary.loc[keep_idx, 'last_reg'] = last_reg

        for idx in group.index:
            if idx != keep_idx:
                merge_map[group.loc[idx, 'tid']] = keep_tid
                rows_to_drop.append(idx)

    if rows_to_drop:
        summary = summary.drop(rows_to_drop).reset_index(drop=True)
        print(f"  Consolidated {len(rows_to_drop)} sub-event entries into parent tournaments")
        # Save merge map for daily data consolidation later
        _tid_merge_map = merge_map
    else:
        _tid_merge_map = {}
else:
    _tid_merge_map = {}

print(f"  {len(summary)} tournaments")
print(f"  {summary['has_timestamps'].sum()} with timestamps")
print(f"  {summary['family'].nunique()} unique families")
print(f"  Years: {summary['tournament_year'].min()}-{summary['tournament_year'].max()}")

# ── Reconcile final_count against live scrape ──────────────────────────────
# all_registrations.csv is a manual snapshot and goes stale between exports.
# daily_scrape.csv is refreshed by auto_update.py and tracks the live entry
# count through tournament close. Whichever source records the higher number
# is closer to truth — use it. This prevents the model from being graded
# against a stale low-water snapshot (see ACO 2026: snapshot 184 vs final 424).
scrape_path = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
_rebased_tids = set()  # filled below; consumed when extending daily_counts
_scrape_for_extension = None
if os.path.exists(scrape_path):
    print("\nReconciling final_count + last_reg against daily_scrape.csv...")
    scrape = pd.read_csv(scrape_path)
    scrape['date'] = pd.to_datetime(scrape['date'])
    # Peak entry_count per tournament_name (gross, includes withdrawn —
    # matches the row-count semantics of all_registrations.csv).
    scrape_peak = (scrape.groupby('tournament_name')['entry_count']
                          .max()
                          .reset_index()
                          .rename(columns={'entry_count': 'scrape_peak'}))
    # Latest scrape date with non-zero entries — used to rebase last_reg
    # so the cumulative-curve T axis covers the late-registration tail.
    scrape_latest = (scrape[scrape['entry_count'] > 0]
                     .groupby('tournament_name')['date'].max()
                     .reset_index()
                     .rename(columns={'date': 'scrape_last_date'}))
    summary = summary.merge(scrape_peak, on='tournament_name', how='left')
    summary = summary.merge(scrape_latest, on='tournament_name', how='left')

    # 1) Reconcile final_count
    pre_count = summary['final_count'].copy()
    summary['final_count'] = summary[['final_count', 'scrape_peak']].max(axis=1)
    summary['final_count'] = summary['final_count'].astype(int)
    bumped = summary[summary['final_count'] > pre_count].copy()
    if len(bumped) > 0:
        bumped['delta'] = bumped['final_count'] - pre_count[bumped.index]
        print(f"  Reconciled final_count for {len(bumped)} tournament(s):")
        for _, r in bumped.sort_values('delta', ascending=False).iterrows():
            print(f"    {r['tournament_name']:<55} snapshot={pre_count[r.name]:>5} → scrape={r['final_count']:>5} (+{r['delta']})")
    else:
        print("  No final_count reconciliation needed.")

    # 2) Rebase last_reg where scrape extends past snapshot
    summary['last_reg'] = pd.to_datetime(summary['last_reg'])
    rebase_mask = (summary['scrape_last_date'].notna() &
                   (summary['scrape_last_date'] > summary['last_reg']))
    rebased = summary[rebase_mask].copy()
    if len(rebased) > 0:
        print(f"  Rebasing last_reg for {len(rebased)} tournament(s) with post-snapshot scrape data:")
        for _, r in rebased.iterrows():
            print(f"    {r['tournament_name']:<55} {r['last_reg'].date()} → {r['scrape_last_date'].date()}")
        summary.loc[rebase_mask, 'last_reg'] = summary.loc[rebase_mask, 'scrape_last_date']
        _rebased_tids = set(summary.loc[rebase_mask, 'tid'].tolist())
        _scrape_for_extension = scrape  # consumed below to extend daily_counts
    summary = summary.drop(columns=['scrape_peak', 'scrape_last_date'])
else:
    print(f"\n  WARN: {scrape_path} not found — skipping reconciliation. "
          "final_count may be stale.")

# ── Compute Days-Before-Event ───────────────────────────────────────────────
# Use last_reg as proxy for event date (last registration ≈ day 1 of tournament)
print("\nComputing days-before-event for timestamped registrations...")

# Merge last_reg onto individual registrations
df = df.merge(summary[['tid', 'last_reg', 'final_count']], on='tid', how='left')

# days_before_event: positive = before event, 0 = event day
df['days_before_event'] = (df['last_reg'] - df['registered_time']).dt.total_seconds() / 86400
df.loc[df['days_before_event'] < 0, 'days_before_event'] = 0  # clamp

# ── Cumulative Registration Curves ──────────────────────────────────────────
print("\nBuilding cumulative registration curves for timestamped tournaments...")

# For each timestamped tournament, compute cumulative % at each day-before-event
ts_mask = df['registered_time'].notna()
ts_df = df[ts_mask].copy()

# Drop rows where days_before_event is NaN (e.g., tid filtered out of summary)
ts_df = ts_df[ts_df['days_before_event'].notna()].copy()

# Bin into integer days before event
ts_df['T'] = ts_df['days_before_event'].apply(np.floor).astype(int)

# Compute daily registration counts per tournament
daily_counts = ts_df.groupby(['tid', 'T']).size().reset_index(name='daily_regs')

# Compute cumulative (from earliest to event day, so reverse T)
# Sort so T descending (earliest registrations first), then cumsum within each tid
daily_counts = daily_counts.sort_values(['tid', 'T'], ascending=[True, False])
daily_counts['cum_regs'] = daily_counts.groupby('tid')['daily_regs'].cumsum()
tid_totals = daily_counts.groupby('tid')['daily_regs'].transform('sum')
daily_counts['cum_pct'] = daily_counts['cum_regs'] / tid_totals

# ── Consolidate daily data for merged sub-events ──────────────────────────
if _tid_merge_map:
    daily_counts['tid'] = daily_counts['tid'].map(
        lambda t: _tid_merge_map.get(t, t))
    daily_counts = daily_counts.groupby(['tid', 'T']).agg(
        daily_regs=('daily_regs', 'sum'),
    ).reset_index()
    daily_counts = daily_counts.sort_values(['tid', 'T'], ascending=[True, False])
    daily_counts['cum_regs'] = daily_counts.groupby('tid')['daily_regs'].cumsum()
    tid_totals = daily_counts.groupby('tid')['daily_regs'].transform('sum')
    daily_counts['cum_pct'] = daily_counts['cum_regs'] / tid_totals
    print(f"  Consolidated daily data for {len(_tid_merge_map)} merged sub-events")

# ── Extend curve with scrape data for rebased tournaments ─────────────────
# Snapshot timestamps end at the manual export date. For tournaments whose
# registrations continued past that date, the curve is missing its tail —
# which is exactly the window the model's short-lead-time predictions
# (T-14, T-7, T-3) need. Inject scrape rows so cum_regs at every T reflects
# reality, not the truncated snapshot.
if _rebased_tids and _scrape_for_extension is not None:
    print(f"\nExtending daily curve with scrape data for {len(_rebased_tids)} rebased tournament(s)...")
    rebased_summary = summary[summary['tid'].isin(_rebased_tids)][['tid', 'tournament_name', 'last_reg', 'final_count']]
    extension_rows = []
    for _, r in rebased_summary.iterrows():
        sc_rows = _scrape_for_extension[_scrape_for_extension['tournament_name'] == r['tournament_name']].copy()
        if len(sc_rows) == 0:
            continue
        sc_rows = sc_rows.sort_values('date')
        sc_rows['T'] = (r['last_reg'] - sc_rows['date']).dt.days
        # Drop scrape rows past the new last_reg (negative T) and zero-entry rows
        sc_rows = sc_rows[(sc_rows['T'] >= 0) & (sc_rows['entry_count'] > 0)]
        for _, sr in sc_rows.iterrows():
            extension_rows.append({
                'tid': r['tid'], 'T': int(sr['T']),
                'cum_regs': int(sr['entry_count']),
                'source': 'scrape',
            })

    if extension_rows:
        ext_df = pd.DataFrame(extension_rows)
        # Combine archive + scrape, take running max of cum_regs per tid in
        # chronological order (T descending), then derive daily_regs.
        archive_view = daily_counts[daily_counts['tid'].isin(_rebased_tids)][['tid', 'T', 'cum_regs']].copy()
        archive_view['source'] = 'archive'
        combined = pd.concat([archive_view, ext_df], ignore_index=True)
        # When archive and scrape have the same T, prefer scrape (it includes
        # late registrations the archive's individual timestamps may have missed).
        combined = combined.sort_values(['tid', 'T', 'source'], ascending=[True, False, True])
        combined = combined.drop_duplicates(subset=['tid', 'T'], keep='last')
        # Running max of cum_regs in chronological order (largest T first → smallest)
        combined = combined.sort_values(['tid', 'T'], ascending=[True, False])
        combined['cum_regs'] = combined.groupby('tid')['cum_regs'].cummax()
        combined['daily_regs'] = combined.groupby('tid')['cum_regs'].diff().fillna(combined['cum_regs']).astype(int)
        combined['cum_regs'] = combined['cum_regs'].astype(int)
        combined = combined[['tid', 'T', 'daily_regs', 'cum_regs']]

        # Replace rebased tids' rows in daily_counts with the merged version
        daily_counts = pd.concat([
            daily_counts[~daily_counts['tid'].isin(_rebased_tids)],
            combined,
        ], ignore_index=True)
        # Recompute cum_pct using reconciled final_count as the tournament total
        finals = summary.set_index('tid')['final_count']
        daily_counts['cum_pct'] = daily_counts.apply(
            lambda r: r['cum_regs'] / finals[r['tid']] if r['tid'] in finals.index and finals[r['tid']] > 0 else 0.0,
            axis=1,
        )
        added = sum(1 for _ in extension_rows)
        print(f"  Injected {added} scrape rows; combined curves now span "
              f"T=[{combined['T'].min()}..{combined['T'].max()}]")

# ── Detect Early-Bird Spikes ────────────────────────────────────────────────
print("\nDetecting early-bird spikes...")

spike_results = []
for tid, group in daily_counts.groupby('tid'):
    window = group[(group['T'] >= 55) & (group['T'] <= 75)]
    baseline_region = group[(group['T'] >= 76) & (group['T'] <= 90)]

    if len(window) == 0 or len(baseline_region) == 0:
        spike_results.append({'tid': tid, 'early_bird_spike': False, 'spike_day': None, 'spike_magnitude': 0})
        continue

    baseline_rate = max(baseline_region['daily_regs'].median(), 1)
    peak_idx = window['daily_regs'].idxmax()
    peak_row = window.loc[peak_idx]
    magnitude = peak_row['daily_regs'] / baseline_rate

    spike_results.append({
        'tid': tid,
        'early_bird_spike': magnitude >= 5,
        'spike_day': int(peak_row['T']),
        'spike_magnitude': round(magnitude, 1)
    })

spike_results = pd.DataFrame(spike_results)
summary = summary.merge(spike_results, on='tid', how='left')
summary['early_bird_spike'] = summary['early_bird_spike'].fillna(False)

n_spikes = summary['early_bird_spike'].sum()
print(f"  {n_spikes} tournaments with detected early-bird spikes")

# ── Save Summary ────────────────────────────────────────────────────────────
summary_path = os.path.join(OUTPUT_DIR, "tournament_summary.csv")
summary.to_csv(summary_path, index=False)
print(f"\nSaved tournament summary to {summary_path}")

# Save daily counts for use in later phases
daily_path = os.path.join(OUTPUT_DIR, "daily_registration_counts.csv")
daily_counts.to_csv(daily_path, index=False)
print(f"Saved daily registration counts to {daily_path}")

# ── EDA: Chicago Open Cumulative Curves ─────────────────────────────────────
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
print(f"\nSaved Chicago Open curves plot to output/chicago_open_curves.png")

# ── EDA: Family Size Distribution ───────────────────────────────────────────
family_counts = summary.groupby('family').agg(
    n_editions=('tid', 'size'),
    n_timestamped=('has_timestamps', 'sum'),
    mean_count=('final_count', 'mean'),
    min_year=('tournament_year', 'min'),
    max_year=('tournament_year', 'max'),
).sort_values('n_editions', ascending=False)

print(f"\n── Top 20 Tournament Families by Edition Count ──")
print(family_counts.head(20).to_string())

family_counts.to_csv(os.path.join(OUTPUT_DIR, "family_stats.csv"))

# ── EDA: Year-over-Year Trends ──────────────────────────────────────────────
yearly = summary[~summary['is_online']].groupby('tournament_year').agg(
    n_tournaments=('tid', 'size'),
    total_registrations=('final_count', 'sum'),
    mean_per_tournament=('final_count', 'mean'),
    median_per_tournament=('final_count', 'median'),
).reset_index()

print(f"\n── Year-over-Year Summary (in-person only) ──")
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
print(f"Saved yearly trends plot to output/yearly_trends.png")

# ── Summary Stats ───────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"PHASE 1 COMPLETE")
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
