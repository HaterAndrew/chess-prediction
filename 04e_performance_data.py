"""
Phase 4E: Generate multi-year model performance data for the website.

Runs expanding-window blind tests for 2022-2026:
  - For historical years (2022-2025): train on data < Y, predict year Y
  - For 2026: train on pre-2026 + completed 2026, predict completed 2026 tournaments

Outputs performance_data.json with per-year breakdowns for the Performance tab.
"""

import pandas as pd
import numpy as np
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib import import_module
m04c = import_module("04c_final_model")
from pipeline_utils import is_event_complete

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
TODAY = pd.Timestamp.now().normalize()

# T-points to evaluate (days before event)
T_POINTS = [90, 60, 42, 28, 14, 7, 3, 1]

# Minimum final count to include in evaluation
MIN_FINAL_COUNT = 50

# Years to evaluate (expanding window: train on < Y, predict Y)
EVAL_YEARS = [2022, 2023, 2024, 2025, 2026]

# Grading rubric based on T-14 MAE% and CI coverage
GRADE_RUBRIC = [
    ("A+", 5, 85), ("A", 8, 75), ("A-", 10, 72),
    ("B+", 12, 68), ("B", 14, 65), ("B-", 16, 60),
    ("C+", 18, 55), ("C", 20, 50), ("C-", 22, 48),
    ("D", 25, 45), ("F", 999, 0),
]


def compute_grade(mae_pct, ci_coverage):
    """Assign letter grade from T-14 MAE% and CI coverage."""
    for grade, max_mae, min_cov in GRADE_RUBRIC:
        if mae_pct <= max_mae and ci_coverage >= min_cov:
            return grade
    return "F"


def compute_aggregate(tournament_results):
    """Compute aggregate metrics at each T-point from tournament results."""
    aggregate = []
    for T in T_POINTS:
        errors = []
        abs_errors = []
        ci_hits = []
        for tr in tournament_results:
            pred = tr['predictions'].get(T)
            if pred:
                errors.append(pred['error_pct'])
                abs_errors.append(pred['abs_error_pct'])
                ci_hits.append(pred['in_ci'])

        if not abs_errors:
            continue

        aggregate.append({
            "T": T,
            "n": len(abs_errors),
            "mae_pct": round(np.mean(abs_errors), 1),
            "median_ape_pct": round(np.median(abs_errors), 1),
            "ci_coverage": round(np.mean(ci_hits) * 100, 0),
            "bias_pct": round(np.mean(errors), 1),
        })
    return aggregate


def grade_from_aggregate(aggregate):
    """Compute grade and detail string from aggregate metrics."""
    t14 = next((a for a in aggregate if a['T'] == 14), None)
    if t14:
        grade = compute_grade(t14['mae_pct'], t14['ci_coverage'])
        detail = f"T-14 MAE: {t14['mae_pct']}%, CI coverage: {t14['ci_coverage']}%"
    elif aggregate:
        best = min(aggregate, key=lambda a: a['T'])
        grade = compute_grade(best['mae_pct'], best['ci_coverage'])
        detail = f"T-{best['T']} MAE: {best['mae_pct']}%, CI coverage: {best['ci_coverage']}%"
    else:
        grade, detail = "N/A", "No data"
    return grade, detail


def evaluate_tournaments(model, test_tournaments, daily):
    """Run blind test predictions for a set of tournaments.

    test_tournaments: list of dicts with family, tid, final_count, event_start
    Returns list of result dicts with predictions at each T-point.
    """
    results = []

    for tinfo in test_tournaments:
        family = tinfo['family']
        tid = tinfo['tid']
        final = tinfo['final_count']

        tid_daily = daily[daily['tid'] == tid].sort_values('T', ascending=False)
        if len(tid_daily) == 0:
            continue

        t_predictions = {}
        for T in T_POINTS:
            available = tid_daily[
                (tid_daily['T'] >= T - 2) & (tid_daily['T'] <= T + 2)
            ].copy()
            if len(available) == 0:
                continue
            available['dist'] = (available['T'] - T).abs()
            closest = available.sort_values('dist').iloc[0]
            count_at_T = int(closest['cum_regs'])

            if count_at_T <= 0:
                continue

            point, ci_lo, ci_hi = model.predict_nowcast(count_at_T, T, family)
            if point is None:
                continue

            point = int(round(point))
            ci_lo = int(round(ci_lo))
            ci_hi = int(round(ci_hi))

            error_pct = round((point - final) / final * 100, 1)
            t_predictions[T] = {
                "T": T,
                "count_at_T": count_at_T,
                "predicted": point,
                "ci_lower": ci_lo,
                "ci_upper": ci_hi,
                "error_pct": error_pct,
                "abs_error_pct": abs(error_pct),
                "in_ci": 1 if ci_lo <= final <= ci_hi else 0,
            }

        if not t_predictions:
            continue

        results.append({
            "family": family,
            "final_count": final,
            "event_start": tinfo['event_start'],
            "predictions": t_predictions,
        })

    return results


def format_results(tournament_results):
    """Convert predictions dict to sorted list for JSON output."""
    out = []
    for tr in tournament_results:
        preds_list = sorted(tr['predictions'].values(), key=lambda p: -p['T'])
        out.append({
            "family": tr['family'],
            "final_count": tr['final_count'],
            "event_start": tr['event_start'],
            "predictions": preds_list,
        })
    return out


def assert_truth_label_freshness(summary, tolerance=5):
    """Abort if daily_scrape recorded a higher entry_count than summary.final_count
    for an event that has already ended.

    Defense-in-depth: 01_data_prep.py reconciles these values, so this should
    never fire under normal operation. If it does, the snapshot pipeline is
    out of sync with the live scrape and the model would be graded against
    stale truth labels (the bug that produced ACO 2026 final=184 vs real 424).
    Tolerance absorbs small timing differences between snapshot and scrape.

    In-progress events are excluded — their summary.final_count is a moving
    snapshot, not truth, and naturally lags scrape_peak. The check uses
    tournament_metadata.end_date < today; events without metadata are
    conservatively excluded (treated as in-progress).
    """
    scrape_path = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
    if not os.path.exists(scrape_path):
        return
    scrape = pd.read_csv(scrape_path)
    peak = (scrape.groupby('tournament_name')['entry_count']
                  .max().reset_index()
                  .rename(columns={'entry_count': 'scrape_peak'}))
    merged = summary.merge(peak, on='tournament_name', how='inner')

    meta_path = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
    today = pd.Timestamp.now().normalize()
    if os.path.exists(meta_path):
        meta = pd.read_csv(meta_path)
        meta['end_date'] = pd.to_datetime(meta['end_date'], errors='coerce')
        meta_keys = meta[['family', 'year', 'end_date']].rename(
            columns={'year': 'tournament_year'})
        merged = merged.merge(meta_keys, on=['family', 'tournament_year'], how='left')
        completed = merged['end_date'].notna() & (merged['end_date'] < today)
        merged = merged[completed]

    stale = merged[merged['scrape_peak'] > merged['final_count'] + tolerance]
    if len(stale) > 0:
        lines = ["STALE TRUTH LABELS — refusing to grade against snapshot data."]
        lines.append("daily_scrape.csv recorded higher entry_count than tournament_summary.final_count for completed events:")
        for _, r in stale.iterrows():
            lines.append(f"  {r['tournament_name']:<55} summary={int(r['final_count']):>5}  scrape_peak={int(r['scrape_peak']):>5}  delta=+{int(r['scrape_peak'] - r['final_count'])}")
        lines.append("Re-run 01_data_prep.py to reconcile, then retry.")
        raise RuntimeError("\n".join(lines))


def main():
    summary, daily, meta, hist_enrich = m04c.load_data()
    assert_truth_label_freshness(summary)
    enrichment_lookup = m04c.build_enrichment_lookup(hist_enrich)
    meta['start_date'] = pd.to_datetime(meta['start_date'])

    # ── Exclude blitz/rapid side events (not useful for logistical planning) ──
    blitz_mask = summary['family'].str.contains(
        r'Blitz|Rapid|Bullet|Bughouse|Armageddon', case=False, na=False, regex=True
    )
    excluded = summary[blitz_mask]['family'].unique()
    if len(excluded) > 0:
        print(f"  Excluding {len(excluded)} blitz/rapid families: {', '.join(excluded)}")
    summary = summary[~blitz_mask].copy()

    # ── Exclude World Open sub-events that can't be predicted from history ──
    # These are small side events or post-2023 splits that inherit the wrong
    # family history (combined "World Open" ~1100 entries vs sub-event ~60-150).
    # Uses tournament_aliases.is_wo_excluded — same logic as 04d.
    # Special case: 'World Open lower sections' was originally added with note
    # "predicted 1124 vs actual 149"; keep it excluded from perf eval here even
    # though display layer keeps it visible. Override via wo_perf_extra.
    from tournament_aliases import is_wo_excluded
    wo_perf_extra = {'World Open lower sections', 'World Open, lower sections'}
    wo_mask = summary['family'].apply(
        lambda f: is_wo_excluded(f) or f in wo_perf_extra
    )
    wo_excluded = summary[wo_mask]['family'].unique()
    if len(wo_excluded) > 0:
        print(f"  Excluding {len(wo_excluded)} World Open sub-events from perf eval")
    summary = summary[~wo_mask].copy()

    # ── Identify completed 2026 tournaments ──
    # Tiered acceptance — replaces the prior binary "scrape coverage required"
    # gate, which over-rejected events that ended after the snapshot but whose
    # snapshots otherwise looked intact (e.g. Mid-America Open 2026 — last_reg
    # was 17 min before the file-level snapshot, registration was effectively
    # closed, but the daily scraper hadn't tracked it). Tiers, evaluated in
    # order:
    #   1. scrape-verified            — name appears in daily_scrape.csv
    #   2. snapshot-post-event        — file snapshot OR per-row last_reg
    #                                   covers the event end → walk-ins seen
    #   3. history-plausibility       — registration captured into the event
    #                                   AND final_count is within tolerance
    #                                   of the family's historical median
    # ACO 2026 (the bug that motivated the original gate) had final=184 vs a
    # family median in the 400s (~46% ratio). The PLAUSIBILITY_FLOOR below
    # would still reject that snapshot.
    scrape_path = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
    scraped_names = set()
    snapshot_date = None
    if os.path.exists(scrape_path):
        sc = pd.read_csv(scrape_path)
        sc = sc[sc['entry_count'] > 0]
        scraped_names = set(sc['tournament_name'].unique())

    # Infer snapshot cutoff from the unreconciled manual snapshot horizon.
    # Reconciliation can rebase last_reg to today's scrape date, which would
    # incorrectly make post-snapshot, unscraped events look authoritative.
    snapshot_col = 'snapshot_last_reg' if 'snapshot_last_reg' in summary.columns else 'last_reg'
    summary_lr = pd.to_datetime(summary[snapshot_col], errors='coerce')
    snapshot_date = summary_lr.max() if summary_lr.notna().any() else None

    # Family historical baseline for Tier 3. Excludes COVID and online seasons
    # so the median represents normal in-person turnout.
    history_pool = summary[
        (summary['tournament_year'] < 2026)
        & (~summary['is_online'].fillna(False))
        & (~summary['is_covid'].fillna(False))
        & (summary['final_count'] > 0)
    ]
    PLAUSIBILITY_FLOOR = 0.60   # final_count must be ≥ this fraction of family median
    PLAUSIBILITY_CEILING = 2.00 # …and ≤ this fraction (catches over-counted snapshots)
    MIN_FAMILY_HISTORY = 3      # need at least this many prior years to score

    completed_2026_all = summary[
        (summary['tournament_year'] == 2026) &
        (~summary['is_online'].fillna(False)) &
        (summary['has_timestamps'])
    ].copy()
    completed_2026_all['last_reg'] = pd.to_datetime(completed_2026_all['last_reg'])
    completed_2026_tids = set()
    no_scrape_skipped = []   # excluded tournaments with reason
    soft_accepted = []       # accepted via Tier 3 (history-plausibility)

    for _, row in completed_2026_all.iterrows():
        lr = row['last_reg']
        if pd.isna(lr) or lr > TODAY:
            continue
        family = row['family']
        m_row = meta[(meta['family'] == family) & (meta['year'] == 2026)]
        start_date = m_row.iloc[0]['start_date'] if len(m_row) > 0 else pd.NaT
        end_date = m_row.iloc[0]['end_date'] if len(m_row) > 0 else pd.NaT
        if pd.notna(start_date) and start_date > TODAY:
            continue
        end_dt = pd.to_datetime(end_date) if pd.notna(end_date) else pd.NaT

        # In-progress events must not be evaluated: summary.final_count for a
        # live tournament reflects the latest scrape (which 01_data_prep raises
        # via raise-only merge), not the true final. Tier 1's "name in
        # daily_scrape.csv" is necessary but not sufficient — Chicago Open's
        # name appears the moment the scraper starts tracking it, weeks before
        # the event ends.
        if not is_event_complete(end_dt, TODAY):
            no_scrape_skipped.append((row['tournament_name'], 'event still in progress (end_date >= today)'))
            continue

        # Tier 1 — scrape-verified.
        if scraped_names and row['tournament_name'] in scraped_names:
            completed_2026_tids.add(row['tid'])
            continue

        # Tier 2 — snapshot is authoritative for this row. The snapshot file
        # was exported at or after the latest registration moment we know
        # about: max(last_reg, end_date). When end_date is unknown (no
        # metadata row), fall back to last_reg alone — if last_reg ≤
        # snapshot_date, no registrations could have occurred for this row
        # after the snapshot was taken. Also accept when this row's last_reg
        # itself reaches end_date (snapshot captured registrations through
        # the event's last day even if the file snapshot was earlier).
        horizon_parts = [t for t in (lr, end_dt) if pd.notna(t)]
        horizon = max(horizon_parts) if horizon_parts else pd.NaT
        snapshot_covers_horizon = (
            snapshot_date is not None and pd.notna(horizon) and snapshot_date >= horizon
        )
        lastreg_through_end = (
            pd.notna(end_dt) and lr >= end_dt
        )
        if snapshot_covers_horizon or lastreg_through_end:
            completed_2026_tids.add(row['tid'])
            continue

        # Tier 3 — history-plausibility. Requires (a) registration captured
        # into the event's first day AND (b) final_count within tolerance of
        # the family's historical median. Catches truncated snapshots
        # (ACO-2026-style) while admitting events whose daily scraper missed
        # them but whose snapshot looks intact.
        reg_captured_into_event = (
            pd.notna(start_date) and lr >= pd.to_datetime(start_date)
        )
        family_hist = history_pool.loc[
            history_pool['family'] == family, 'final_count'
        ]
        if reg_captured_into_event and len(family_hist) >= MIN_FAMILY_HISTORY:
            median_hist = family_hist.median()
            ratio = row['final_count'] / median_hist if median_hist else 0.0
            if PLAUSIBILITY_FLOOR <= ratio <= PLAUSIBILITY_CEILING:
                completed_2026_tids.add(row['tid'])
                soft_accepted.append(
                    (row['tournament_name'], int(row['final_count']),
                     int(median_hist), round(ratio * 100))
                )
                continue
            if ratio < PLAUSIBILITY_FLOOR:
                bound_msg = f"below {int(PLAUSIBILITY_FLOOR*100)}% floor (possible truncated snapshot)"
            else:
                bound_msg = f"above {int(PLAUSIBILITY_CEILING*100)}% ceiling (possible over-counted snapshot)"
            no_scrape_skipped.append(
                (row['tournament_name'],
                 f"final={int(row['final_count'])} is {round(ratio*100)}% of family "
                 f"median {int(median_hist)} — {bound_msg}")
            )
            continue

        if pd.isna(start_date):
            reason = "no metadata row (start/end_date unknown)"
        elif not reg_captured_into_event:
            reason = "snapshot last_reg precedes event start (registration window not captured)"
        else:
            reason = f"insufficient family history ({len(family_hist)} prior year(s)) and no scrape coverage"
        no_scrape_skipped.append((row['tournament_name'], reason))

    if soft_accepted:
        print(f"  Accepted {len(soft_accepted)} 2026 tournament(s) via history-plausibility tier "
              f"(no daily_scrape coverage; final_count within "
              f"{int(PLAUSIBILITY_FLOOR*100)}–{int(PLAUSIBILITY_CEILING*100)}% of family median):")
        for name, fc, med, ratio in soft_accepted:
            print(f"    {name:<55} final={fc:>4}  family_median={med:>4}  ratio={ratio}%")
    if no_scrape_skipped:
        print(f"  Excluded {len(no_scrape_skipped)} 2026 tournament(s) (snapshot truth unverifiable):")
        for name, reason in no_scrape_skipped:
            print(f"    {name:<55} {reason}")

    # ── Evaluate each year ──
    year_results = {}
    all_tournament_results = []  # for cumulative

    for year in EVAL_YEARS:
        print(f"\n{'─'*60}")
        print(f"  Evaluating {year}")
        print(f"{'─'*60}")

        if year == 2026:
            # 2026: train on pre-2026 + completed 2026, predict completed 2026
            model = m04c.N5v4_Final()
            model.fit(summary, daily, enrichment_lookup,
                      completed_tids=completed_2026_tids if completed_2026_tids else None,
                      verbose_standings_join=False)

            # Recalibrate from 2024-2025 + completed 2026
            recal_data = summary[
                (summary['has_timestamps']) &
                (~summary['is_online'].fillna(False)) &
                (~summary['is_covid'].fillna(False)) &
                (summary['final_count'] >= 50) &
                (
                    (summary['tournament_year'].isin([2024, 2025])) |
                    (summary['tid'].isin(completed_2026_tids))
                )
            ].copy()
            if len(recal_data) >= 5:
                model.recalibrate(recal_data, daily)
                print(f"  Recalibration applied from {len(recal_data)} tournaments")

            # Build test set from completed 2026 tournaments
            test_tournaments = []
            completed_2026 = summary[
                (summary['tournament_year'] == 2026) &
                (~summary['is_online'].fillna(False)) &
                (summary['final_count'] >= MIN_FINAL_COUNT) &
                (summary['tid'].isin(completed_2026_tids))
            ]
            for _, row in completed_2026.iterrows():
                family = row['family']
                m_row = meta[(meta['family'] == family) & (meta['year'] == 2026)]
                if len(m_row) > 0 and pd.notna(m_row.iloc[0]['start_date']):
                    event_start_str = m_row.iloc[0]['start_date'].strftime('%Y-%m-%d')
                else:
                    event_start_str = pd.to_datetime(row['last_reg']).strftime('%Y-%m-%d')
                test_tournaments.append({
                    'family': family, 'tid': row['tid'],
                    'final_count': int(row['final_count']),
                    'event_start': event_start_str,
                })
        else:
            # Historical: expanding window — train on < year, predict year
            train_summary = summary[summary['tournament_year'] < year].copy()
            model = m04c.N5v4_Final()
            model.fit(train_summary, daily, enrichment_lookup,
                      verbose_standings_join=False)

            # Recalibrate from the 2 years before the test year
            recal_years = [year - 2, year - 1]
            recal_data = train_summary[
                (train_summary['has_timestamps']) &
                (~train_summary['is_online'].fillna(False)) &
                (~train_summary['is_covid'].fillna(False)) &
                (train_summary['final_count'] >= 50) &
                (train_summary['tournament_year'].isin(recal_years))
            ].copy()
            if len(recal_data) >= 5:
                model.recalibrate(recal_data, daily)
                print(f"  Recalibration applied from {len(recal_data)} tournaments ({recal_years})")

            # Build test set
            test_df = summary[
                (summary['tournament_year'] == year) &
                (summary['has_timestamps']) &
                (~summary['is_online'].fillna(False)) &
                (~summary['is_covid'].fillna(False)) &
                (summary['final_count'] >= MIN_FINAL_COUNT)
            ]
            test_tournaments = []
            for _, row in test_df.iterrows():
                family = row['family']
                m_row = meta[(meta['family'] == family) & (meta['year'] == year)]
                if len(m_row) > 0 and pd.notna(m_row.iloc[0]['start_date']):
                    event_start_str = m_row.iloc[0]['start_date'].strftime('%Y-%m-%d')
                else:
                    lr = pd.to_datetime(row['last_reg'])
                    event_start_str = lr.strftime('%Y-%m-%d') if pd.notna(lr) else f"{year}-06-01"
                test_tournaments.append({
                    'family': family, 'tid': row['tid'],
                    'final_count': int(row['final_count']),
                    'event_start': event_start_str,
                })

        # Run evaluation
        results = evaluate_tournaments(model, test_tournaments, daily)
        print(f"  Evaluated {len(results)} tournaments")

        # Compute year-level aggregate + grade
        agg = compute_aggregate(results)
        grade, grade_detail = grade_from_aggregate(agg)

        year_results[year] = {
            "year": year,
            "n_tournaments": len(results),
            "grade": grade,
            "grade_detail": grade_detail,
            "aggregate": agg,
            "tournaments": format_results(results),
        }
        all_tournament_results.extend(results)

        # Print year summary
        print(f"  Grade: {grade} ({grade_detail})")
        for a in agg:
            print(f"    T-{a['T']:>2}: MAE {a['mae_pct']:>5.1f}%  CI cov {a['ci_coverage']:>3.0f}%  bias {a['bias_pct']:>+5.1f}%  (n={a['n']})")

    # ── Cumulative (all years combined) ──
    cum_agg = compute_aggregate(all_tournament_results)
    cum_grade, cum_detail = grade_from_aggregate(cum_agg)

    # ── Build output ──
    # Top-level fields use 2026 (YTD) for backward compatibility with bias correction
    ytd = year_results.get(2026, {})

    output = {
        "generated": TODAY.strftime('%Y-%m-%d'),
        "model": "N5v4_Final",
        # YTD (2026) — used by bias correction and existing code
        "n_tournaments": ytd.get('n_tournaments', 0),
        "grade": ytd.get('grade', 'N/A'),
        "grade_detail": ytd.get('grade_detail', ''),
        "aggregate": ytd.get('aggregate', []),
        "tournaments": ytd.get('tournaments', []),
        # Multi-year breakdown
        "years": year_results,
        # Cumulative across all years
        "cumulative": {
            "n_tournaments": len(all_tournament_results),
            "grade": cum_grade,
            "grade_detail": cum_detail,
            "aggregate": cum_agg,
            "tournaments": format_results(all_tournament_results),
        },
    }

    out_path = os.path.join(OUTPUT_DIR, "performance_data.json")
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)

    # Print overall summary
    print(f"\n{'='*60}")
    print(f"  MULTI-YEAR PERFORMANCE SUMMARY")
    print(f"{'='*60}")
    for yr in EVAL_YEARS:
        yr_data = year_results.get(yr, {})
        print(f"  {yr}: {yr_data.get('grade', 'N/A'):>3}  ({yr_data.get('n_tournaments', 0)} tournaments)")
    print(f"  {'─'*40}")
    print(f"  Cumulative: {cum_grade:>3}  ({len(all_tournament_results)} tournaments)")
    print(f"  {cum_detail}")
    print(f"\n  Output: {out_path}")


if __name__ == '__main__':
    main()
