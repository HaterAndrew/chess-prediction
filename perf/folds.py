"""Fold preparation + expanding-window year folds (04e main() body,
verbatim; the A/B sections become prepare_folds, the year loop
run_year_folds).
"""
import os
import sys

import pandas as pd

# The digit-prefixed 04c shim needs import_module; insert the repo root
# (this file lives one level down).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from importlib import import_module
m04c = import_module("04c_final_model")
from pipeline_utils import (clamp_stats,
                            is_event_complete, reset_clamp_stats)
from shared.clock import today_ts
from shared.paths import OUTPUT_DIR
from shared.thresholds import FROZEN_CURVE_MIN_RATIO, MIN_FINAL_COUNT

from perf.evaluation import (_hist_lookup,
                             assert_truth_label_freshness,
                             evaluate_tournaments, format_results)
from perf.grading import compute_aggregate, grade_from_aggregate

TODAY = today_ts()

# Years to evaluate (expanding window: train on < Y, predict Y)
EVAL_YEARS = [2022, 2023, 2024, 2025, 2026]


def prepare_folds():
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
        #
        # v3 T4 (audit/AUDIT_2026-07-25.md): the 0.60-2.00 band is a weak test
        # for a freeze — a curve frozen at a plausible-looking total sits inside
        # it, and 18 of 20 graded finals do. The band alone cannot distinguish
        # "this family really is that size" from "the export stopped early".
        # It no longer has to: is_curve_gradeable (T1) is an independent
        # freshness check on the curve itself, and it runs on every tournament
        # admitted here before any grade is computed. A soft-accepted event whose
        # curve is frozen is therefore caught downstream rather than graded.
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
    return summary, daily, meta, enrichment_lookup, completed_2026_tids


def run_year_folds(summary, daily, meta, enrichment_lookup, completed_2026_tids):
    year_results = {}
    all_tournament_results = []  # for cumulative

    for year in EVAL_YEARS:
        print(f"\n{'─'*60}")
        print(f"  Evaluating {year}")
        print(f"{'─'*60}")

        if year == 2026:
            # J1: leave-one-out. The prior code fit ONE model on all completed
            # 2026 tids and then predicted those same tids in-sample, inflating
            # the 2026 grade (the headline number). Build the test set, then refit
            # per tournament with that tid held out of BOTH the ratio store and the
            # regression leg, and predict only that tournament. N refits by design —
            # the only fully leak-free option until reg_params carries per-edition
            # provenance.
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
                    'tournament_name': row.get('tournament_name', family),
                    'final_count': int(row['final_count']),
                    'event_start': event_start_str,
                })

            results = []
            frozen_skipped = []
            # Prior-year finals only — the clamp must not see 2026 outcomes, or
            # the leak-free property of the LOO refit above would be undone.
            eval_hist = _hist_lookup(summary[summary['tournament_year'] < 2026])
            reset_clamp_stats()
            for tinfo in test_tournaments:
                loo_tids = completed_2026_tids - {tinfo['tid']}
                model = m04c.N5v4_Final()
                # v3 T5: the LOO fold legitimately trains on the other completed
                # 2026 events, so withhold only this target's own standings and
                # enrichment rows rather than cutting the whole year.
                model.fit(summary, daily, enrichment_lookup,
                          completed_tids=loo_tids if loo_tids else None,
                          verbose_standings_join=False,
                          exclude_family_years={(tinfo['family'], 2026)})
                recal_data = summary[
                    (summary['has_timestamps']) &
                    (~summary['is_online'].fillna(False)) &
                    (~summary['is_covid'].fillna(False)) &
                    (summary['final_count'] >= 50) &
                    (
                        (summary['tournament_year'].isin([2024, 2025])) |
                        (summary['tid'].isin(loo_tids))
                    )
                ].copy()
                if len(recal_data) >= 5:
                    # regime_year: the LOO cohort contains the other completed
                    # 2026 events, so the bias fits on the current regime.
                    model.recalibrate(recal_data, daily, regime_year=year)
                results.extend(evaluate_tournaments(model, [tinfo], daily,
                                                    frozen_skipped=frozen_skipped,
                                                    hist_lookup=eval_hist))
            print(f"  LOO-refit {len(test_tournaments)} completed 2026 tournaments (leak-free)")
            # v3 T2: the eval now runs the display clamp, so report how often it
            # actually altered a graded prediction. If this reads all zeros the
            # published grade and the raw model grade are the same number.
            _cs = clamp_stats()
            _fired = {k: v for k, v in _cs.items() if k != 'calls' and v}
            print(f"  Display clamp: {_cs['calls']} prediction(s) routed through it, "
                  f"{sum(_fired.values())} altered {_fired if _fired else ''}")
            if frozen_skipped:
                # v3 T1: name these loudly. Excluding events from the published
                # grade is a judgement call, and a silent exclusion would be
                # indistinguishable from cherry-picking the grade upward.
                print(f"  Excluded {len(frozen_skipped)} tournament(s) from grading — daily curve "
                      f"frozen below {int(FROZEN_CURVE_MIN_RATIO*100)}% of final "
                      f"(stale export, not a model miss):")
                for name, fc, ratio in frozen_skipped:
                    print(f"    {name:<55} final={fc:>4}  curve peak={round(ratio*100)}% of final")
        else:
            # Historical: expanding window — train on < year, predict year
            train_summary = summary[summary['tournament_year'] < year].copy()
            model = m04c.N5v4_Final()
            # v3 T5: keep the auxiliary joins inside the expanding window too.
            model.fit(train_summary, daily, enrichment_lookup,
                      verbose_standings_join=False, fold_year=year)

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
                # regime_year=year: the cohort ends at year-1, so the regime
                # path stays off and the pooled bias applies (v5 Cat L —
                # year-1 carryover overcorrected the 2024 fold).
                model.recalibrate(recal_data, daily, regime_year=year)
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
                    'tournament_name': row.get('tournament_name', family),
                    'final_count': int(row['final_count']),
                    'event_start': event_start_str,
                })

        # Run evaluation (the 2026 fold already did its own LOO evaluation above)
        if year != 2026:
            frozen_skipped = []
            results = evaluate_tournaments(
                model, test_tournaments, daily,
                frozen_skipped=frozen_skipped,
                # Training years only — same expanding window the model saw.
                hist_lookup=_hist_lookup(train_summary))
            if frozen_skipped:
                print(f"  Excluded {len(frozen_skipped)} tournament(s) from grading — daily curve "
                      f"frozen below {int(FROZEN_CURVE_MIN_RATIO*100)}% of final:")
                for name, fc, ratio in frozen_skipped:
                    print(f"    {name:<55} final={fc:>4}  curve peak={round(ratio*100)}% of final")
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
    return year_results, all_tournament_results
