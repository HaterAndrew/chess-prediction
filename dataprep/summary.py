"""Tournament summary build + scrape reconciliation (01_data_prep,
verbatim). reconcile_with_scrape is the real home of the max-rule that
tests/test_audit_fixes.py used to reimplement inline; it reads
daily_scrape.csv under this module's OUTPUT_DIR (patch the module
attribute in tests).
"""
import os

import pandas as pd

from shared.paths import OUTPUT_DIR


def build_summary(df):
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

    # Preserve the manual snapshot horizon before reconciliation mutates last_reg.
    # 04e_performance_data.py uses this to decide whether a completed 2026 event
    # needs daily_scrape coverage; rebased last_reg values can be as recent as today.
    summary['snapshot_last_reg'] = summary['last_reg']
    return summary, _tid_merge_map


def reconcile_with_scrape(summary):
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

        # Audit-warning trip: if any bumped row belongs to an event whose end_date
        # is today or later, the live tile needs the bump but downstream consumers
        # (04e perf eval, 04d retraining, recalibrate, 06 walk-in) must filter it
        # out via is_event_complete. The auto_update.py harvester picks "WARNING:"
        # lines into output/audit_warnings.json automatically.
        if len(bumped) > 0:
            meta_path = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
            if os.path.exists(meta_path):
                _meta = pd.read_csv(meta_path)
                _meta['end_date'] = pd.to_datetime(_meta['end_date'], errors='coerce')
                _today = pd.Timestamp.now().normalize()
                _live = _meta[_meta['end_date'] >= _today][['family', 'year', 'end_date']]
                _live = _live.rename(columns={'year': 'tournament_year'})
                _check = bumped.merge(_live, on=['family', 'tournament_year'], how='inner')
                if len(_check) > 0:
                    names = ", ".join(_check['tournament_name'].tolist())
                    print(f"  WARNING: raised final_count for {len(_check)} in-progress 2026 event(s) "
                          f"(end_date >= today): {names}. Downstream perf/recalibration "
                          f"scripts must exclude these via is_event_complete.")

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
    return summary, _rebased_tids, _scrape_for_extension
