"""Days-before-event + cumulative curves + scrape extension
(01_data_prep, verbatim).
"""
import numpy as np
import pandas as pd


def build_daily_counts(df, summary, _tid_merge_map):
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
    return daily_counts


def extend_with_scrape(daily_counts, summary, _rebased_tids, _scrape_for_extension):
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
            # When archive and scrape have the same T, keep the higher cumulative
            # count. Scrape usually wins, but archive can legitimately be higher if
            # a scrape row missed withdrawals/cleanup timing.
            combined = (combined.groupby(['tid', 'T'], as_index=False)['cum_regs']
                                .max())
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
            # Recompute cum_pct using reconciled final_count as the tournament total.
            # v3 N7 (audit/AUDIT_2026-07-25.md): this recompute used to run over the
            # WHOLE frame, so rebasing a single tournament re-normalised every other
            # template curve in the dataset against whatever final_count happened to
            # be in summary at the time. Scope it to the tids actually rebased; the
            # rest keep the cum_pct they were built with.
            finals = summary.set_index('tid')['final_count']
            _rebased_mask = daily_counts['tid'].isin(_rebased_tids)

            def _cum_pct(r):
                tid = r['tid']
                if tid in finals.index and finals[tid] > 0:
                    return r['cum_regs'] / finals[tid]
                return 0.0

            daily_counts.loc[_rebased_mask, 'cum_pct'] = daily_counts[_rebased_mask].apply(
                _cum_pct, axis=1)
            added = sum(1 for _ in extension_rows)
            print(f"  Injected {added} scrape rows; combined curves now span "
                  f"T=[{combined['T'].min()}..{combined['T'].max()}]")
    return daily_counts
