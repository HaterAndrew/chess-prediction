"""04d orchestrator: load, fit, cards, metadata, history, output.

The two big loops live in sitebuild.cards / sitebuild.metadata; the rest
is the functionized 04d body verbatim.
"""
import os

import pandas as pd

from pipeline_utils import is_event_complete
from ratio_model import build_ratio_model
from tournament_aliases import canonicalize_family
from shared.season import CURRENT_SEASON, is_open_season

from sitebuild.assemble import finalize_cards
from sitebuild.cards import build_model_cards
from sitebuild.curves import build_template_curves
from sitebuild.helpers import (OUTPUT_DIR, TODAY, _fam_eq, determine_status,
                               m04c)
from sitebuild.history import add_historical_editions
from sitebuild.metadata import build_metadata_cards
from sitebuild.scrape_join import (annotate_editions, consecutive_zero_scrape_days,
                                   counts_by_edition, edition_mask,
                                   latest_by_edition, scrape_daily_series)


def main():
    """Build output/website_data.json. Extracted from module level (P3a):
    importing this module no longer executes the pipeline (G4). Mid-file
    helper defs became closures; behavior is pinned by the golden gate."""

    # Load data
    summary = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_summary.csv"))
    # Coerce tournament_year: fill NaN with 0, convert to int for clean comparisons
    summary['tournament_year'] = pd.to_numeric(summary['tournament_year'], errors='coerce').fillna(0).astype(int)
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "daily_registration_counts.csv"))
    meta = pd.read_csv(os.path.join(OUTPUT_DIR, "tournament_metadata.csv"))
    meta['start_date'] = pd.to_datetime(meta['start_date'])

    # Merge fresh scrape data into summary for every open edition (this season
    # and any later one CCA already lists — see sitebuild.scrape_join).
    # daily_scrape.csv has the latest entry counts from chessaction.com
    # Use active_count (net of withdrawals) when available, fall back to entry_count
    scrape_path = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
    if os.path.exists(scrape_path):
        scrape = pd.read_csv(scrape_path)
        scrape['date'] = pd.to_datetime(scrape['date'])
        # Backfill active_count for older rows that predate the withdrawal columns
        if 'active_count' not in scrape.columns:
            scrape['active_count'] = scrape['entry_count']
        else:
            scrape['active_count'] = scrape['active_count'].fillna(scrape['entry_count'])
        if 'withdrawal_count' not in scrape.columns:
            scrape['withdrawal_count'] = 0
        else:
            scrape['withdrawal_count'] = scrape['withdrawal_count'].fillna(0)
        scrape = annotate_editions(scrape, default_year=CURRENT_SEASON)
        # Get the most recent scrape per edition
        latest_scrape = latest_by_edition(scrape)
        # H13: publish ONE count semantic — gross (row-count, entry_count), matching
        # tournament_summary.csv, the performance tab, the freshness guard, and how
        # 04e grades. The old code overrode final_count with active_count (net), so
        # cards showed net while the perf tab showed gross (ACO 401 vs 424) and the
        # deployed model trained on net but was graded on gross. Track the net/
        # withdrawal delta in a separate column for display instead.
        if 'active_count' not in summary.columns:
            summary['active_count'] = pd.NA
        if 'withdrawal_count' not in summary.columns:
            summary['withdrawal_count'] = pd.NA
        updated = 0
        for _, s in latest_scrape.iterrows():
            # Past-season editions are settled; reconcile_final_counts owns them.
            if not is_open_season(s['year']):
                continue
            mask = edition_mask(summary, s['family'], s['year'])
            gross_count = int(s['entry_count']) if s['entry_count'] > 0 else int(s['active_count'])
            net_count = int(s['active_count']) if s['active_count'] > 0 else gross_count
            if mask.any() and gross_count > 0:
                old_count = summary.loc[mask, 'final_count'].iloc[0]
                summary.loc[mask, 'final_count'] = gross_count
                summary.loc[mask, 'active_count'] = net_count
                summary.loc[mask, 'withdrawal_count'] = max(gross_count - net_count, 0)
                if old_count != gross_count:
                    updated += 1
        # Reanchor ALL daily T values from last_reg to event_start so the model
        # trains and predicts in a consistent coordinate system (T=0 = event start).
        daily = m04c.reanchor_daily_to_event_start(summary, daily, meta)

        # Insert scrape rows using event_start-based T
        for _, s in scrape.iterrows():
            if not is_open_season(s['year']):
                continue
            family_name, edition_year = s['family'], s['year']
            tid_match = summary[edition_mask(summary, family_name, edition_year)]
            if len(tid_match) == 0:
                continue
            tid = tid_match.iloc[0]['tid']
            last_reg = tid_match.iloc[0].get('last_reg')
            meta_row = meta[edition_mask(meta, family_name, edition_year, year_col='year')]
            if len(meta_row) == 0:
                meta_row = meta[(meta['year'] == edition_year) & (meta['start_date'] > pd.Timestamp.now())]
                meta_row = meta_row[meta_row['family'].str.contains(family_name.split()[0], case=False, na=False)]
            if len(meta_row) > 0:
                event_start = pd.to_datetime(meta_row.iloc[0]['start_date'])
                T = max((event_start - pd.to_datetime(s['date'])).days, 0)
            elif pd.notna(last_reg):
                T = max((pd.to_datetime(last_reg) - pd.to_datetime(s['date'])).days, 0)
            else:
                continue
            # Insert or update — use active_count (net) for curve data
            scrape_count = int(s['active_count']) if s['active_count'] > 0 else int(s['entry_count'])
            existing = daily[(daily['tid'] == tid) & (daily['T'] == T)]
            if len(existing) == 0 and scrape_count > 0:
                new_row = pd.DataFrame([{
                    'tid': tid, 'T': T, 'daily_regs': 0,
                    'cum_regs': scrape_count, 'cum_pct': 1.0
                }])
                daily = pd.concat([daily, new_row], ignore_index=True)
            elif len(existing) > 0 and scrape_count > existing.iloc[0]['cum_regs']:
                daily.loc[(daily['tid'] == tid) & (daily['T'] == T), 'cum_regs'] = scrape_count
        print(f"  Merged scrape data: {updated} tournament counts updated, {len(latest_scrape)} tournaments in scrape")

    # Load enrichment data if available
    hist_path = os.path.join(OUTPUT_DIR, "historical_tournaments.csv")
    hist_enrich = pd.read_csv(hist_path) if os.path.exists(hist_path) else pd.DataFrame()
    enrichment_lookup = m04c.build_enrichment_lookup(hist_enrich)

    # Filter exclusions: online, COVID, sub-events we don't want
    # WO exclusion logic lives in tournament_aliases.is_wo_excluded — single
    # source of truth shared with 04e_performance_data.py.
    from tournament_aliases import is_wo_excluded
    _all_families = set(summary['family'].unique()) | set(meta['family'].unique())
    EXCLUDE_FAMILIES = [fam for fam in _all_families if is_wo_excluded(fam)]
    EXCLUDE_FAMILIES.extend([
        # Tiny side events with 1-6 registrants, not real tournaments
        'George Washington Saturday Octos', 'George Washington Sunday Octos',
    ])

    # Exclude all quick-chess side events (not useful for logistical
    # planning). Shared pattern: shared.side_events (also covers Action and
    # G-format events, which the old narrow copy missed).
    from shared.side_events import SIDE_EVENT_PATTERN
    blitz_families = summary[summary['family'].str.contains(
        SIDE_EVENT_PATTERN, case=False, na=False, regex=True
    )]['family'].unique().tolist()
    EXCLUDE_FAMILIES.extend(blitz_families)
    print(f"Excluding {len(blitz_families)} blitz/rapid families")

    # ── Build ratio model (same as N5 but with lognormal CIs) ──



    # ── Determine tournament status ──

    def get_event_date(family, year):
        """Get event start date from metadata, or estimate from historical data."""
        match = meta[_fam_eq(meta['family'], family) & (meta['year'] == year)]
        if len(match) > 0:
            return match.iloc[0]['start_date']

        # Estimate from historical last_reg dates for this family
        fam = summary[_fam_eq(summary['family'], family) & (~summary['is_online'].fillna(False))]
        hist_dates = pd.to_datetime(fam['last_reg'], errors='coerce').dropna()
        if len(hist_dates) > 0:
            avg_month = int(hist_dates.dt.month.median())
            avg_day = int(hist_dates.dt.day.median())
            try:
                return pd.Timestamp(year, avg_month, avg_day)
            except (ValueError, OverflowError):
                pass
        return None


    def get_event_end_date(family, year):
        """Get event end date from metadata."""
        match = meta[_fam_eq(meta['family'], family) & (meta['year'] == year)]
        if len(match) > 0 and pd.notna(match.iloc[0].get('end_date')):
            return pd.to_datetime(match.iloc[0]['end_date'])
        return None




    # ── Build website data ──

    print("Building website data...")

    # Use all non-COVID, non-online data for training
    train = summary[
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False))
    ]
    train_ts = train[train['has_timestamps']]

    # Identify completed 2026 tournaments (last_reg in the past) for rolling retraining
    completed_2026 = summary[
        (summary['tournament_year'] == CURRENT_SEASON) &
        (~summary['is_online'].fillna(False)) &
        (summary['has_timestamps'])
    ].copy()
    completed_2026['last_reg'] = pd.to_datetime(completed_2026['last_reg'])
    completed_tids = set()
    for _, row in completed_2026.iterrows():
        family = row['family']
        lr = row['last_reg']
        if pd.isna(lr) or lr > TODAY:
            continue
        # Require event end_date strictly in the past. A start_date-only check
        # admitted mid-event tournaments (Chicago Open, May 21–25) whose
        # summary.final_count was still being raised by daily scrapes — corrupting
        # prod_model.fit() and recalibrate() with non-final truth labels.
        end_dt = get_event_end_date(family, CURRENT_SEASON)
        if not is_event_complete(end_dt, TODAY):
            continue
        completed_tids.add(row['tid'])

    if completed_tids:
        print(f"  Rolling retraining: {len(completed_tids)} completed 2026 tournaments included in training")

    # Use production model (N5v4_Final) with all fixes:
    # - proper prediction intervals, empirical Bayes shrinkage
    # - expanding-window calibration, T-interpolation
    # - rolling retraining: completed 2026 tournaments fold into training data
    prod_model = m04c.N5v4_Final()
    prod_model.fit(train_ts, daily, enrichment_lookup=enrichment_lookup,
                   completed_tids=completed_tids if completed_tids else None,
                   all_summary_families=set(summary['family'].dropna().unique()))

    # Automated recalibration: learn from ALL completed tournaments (2024-2025 + 2026)
    # Recent data is weighted more heavily (2026 conditions > 2019 conditions)
    recal_data = summary[
        (summary['has_timestamps']) &
        (~summary['is_online'].fillna(False)) &
        (~summary['is_covid'].fillna(False)) &
        (summary['final_count'] >= 50) &
        (
            (summary['tournament_year'].isin([2024, 2025])) |
            (summary['tid'].isin(completed_tids))
        )
    ].copy()
    if len(recal_data) >= 5:
        # regime_year: this model predicts the current year, and the cohort
        # contains its completed events — the bias correction fits on them.
        recal_diag = prod_model.recalibrate(recal_data, daily,
                                            regime_year=int(TODAY.year))
        n_2026 = len(recal_data[recal_data['tournament_year'] == CURRENT_SEASON])
        n_older = len(recal_data) - n_2026
        print(f"  Recalibration from {len(recal_data)} tournaments ({n_older} from 2024-25, {n_2026} from 2026):")
        for T, d in sorted(recal_diag.items()):
            cov = d.get('coverage_before', d.get('coverage', 0))
            print(f"    T-{T:>2}: bias {d['mean_bias']:>+5.1f}% → factor {d['bias_factor']:.3f}, "
                  f"CI cov {cov:>3.0f}% → adj {d['ci_adj']:.3f} (n={d['n']})")
    else:
        print(f"  Recalibration skipped: need ≥5 completed tournaments, have {len(recal_data)}")

    # kept for families without timestamps; completed 2026 tids fold in under the
    # same rolling-retrain policy as prod_model.fit (v5 Cat L — without them no
    # 2026 event could inform a 2026 window prediction).
    ratios = build_ratio_model(train, daily,
                               completed_tids=completed_tids if completed_tids else None)
    curves = build_template_curves(train, daily)

    # ── World Open: keep only Under 13, top 6, lower as separate families ──
    # All other WO sub-events are already in EXCLUDE_FAMILIES.
    # Exclude any remaining WO variants that slipped through naming differences.
    WO_KEEP = {'World Open Under 13', 'World Open top 6 sections', 'World Open lower sections',
               'World Open, top 6 sections', 'World Open, lower sections',
               'World Open Under 13 Championship'}
    wo_extra_exclude = summary[
        (summary['family'].str.startswith('World Open')) &
        (~summary['family'].isin(WO_KEEP))
    ]['family'].unique().tolist()
    if wo_extra_exclude:
        EXCLUDE_FAMILIES.extend(wo_extra_exclude)
        print(f"Excluding {len(wo_extra_exclude)} additional World Open sub-families: {wo_extra_exclude}")
    print(f"World Open: keeping {WO_KEEP & set(summary['family'].unique())}")

    # Every open edition gets a card: this season's, plus next season's events
    # CCA is already taking entries for (2026-09-17: nine 2027 events were open
    # and none showed, because this selected the current season only). The name
    # t2026 predates that; it is the open-edition roster.
    t2026 = summary[
        (summary['tournament_year'] >= CURRENT_SEASON) &
        (~summary['is_online'].fillna(False)) &
        (~summary['family'].isin(EXCLUDE_FAMILIES))
    ].copy()

    # H2 → v5 Cat R: roster-pending skeletons (reconcile_final_counts appended them
    # so the grade universe and freshness guard see the event) carry no registration
    # timestamps — but the model card path does not need them: the scrape merge above
    # already wrote their live counts and injected a full daily curve, and the ratio
    # model trains only on pre-2026 editions. They now STAY in t2026 and are gated
    # per-row inside the loop by roster_pending_model_ok; rows that fail the gate
    # fall through to the metadata loop below exactly as before. Admitted cards keep
    # the roster-pending disclosure via a forced prediction_tier.
    if 'roster_pending' not in t2026.columns:
        t2026['roster_pending'] = False
    t2026['roster_pending'] = t2026['roster_pending'].fillna(False).astype(bool)

    print(f"Found {len(t2026)} open-edition tournaments (after filtering)")

    # Live counts of each scraped edition, (family, year) -> net/gross/wd.
    # Metadata-only tournaments pick their entry counts up from here.
    _scrape_lookup = counts_by_edition(latest_scrape) if os.path.exists(scrape_path) else {}

    # Withdrawal lookup for the model cards. Keyed on the CANONICAL family so
    # comma/whitespace variants between the scraper's spelling and summary rows
    # still match (v5 Cat R), and on the year so two editions stay apart.
    withdrawal_lookup = {
        (canonicalize_family(fam), yr): {'withdrawal_count': c['wd'], 'gross_count': c['gross']}
        for (fam, yr), c in _scrape_lookup.items()
    }

    tournaments_out = []

    build_model_cards(curves, daily, determine_status, get_event_date,
                      get_event_end_date, meta, prod_model, ratios, summary,
                      t2026, tournaments_out, withdrawal_lookup)


    # Add tournaments from metadata that have no registrations yet

    # Consecutive scrape days at 0 entries before a near-event card is relabelled
    # not_tracked (v3 N8). One zero is a scrape hiccup; several in a row is a real
    # cancellation.
    NOT_TRACKED_MIN_ZERO_DAYS = 3

    def _consecutive_zero_scrape_days(family_name, year):
        if not os.path.exists(scrape_path):
            return NOT_TRACKED_MIN_ZERO_DAYS
        return consecutive_zero_scrape_days(scrape, family_name, year,
                                            never_scraped=NOT_TRACKED_MIN_ZERO_DAYS)

    def _scrape_daily_series(family_name, year, fallback_count):
        if not os.path.exists(scrape_path):
            return [[0, int(fallback_count)]], None
        return scrape_daily_series(scrape, family_name, year, fallback_count)

    # Canonical-aware so a metadata event ("... (in Connecticut)") isn't re-added
    # when the main path already emitted its folded form ("Eastern Class
    # Championships") once a fresh export pulls it into the roster.
    # Keyed on the edition: the finished 2026 card of a family must not stop
    # the same family's 2027 metadata card from being added.
    existing_editions = {(canonicalize_family(t['family']), t['year']) for t in tournaments_out}
    build_metadata_cards(EXCLUDE_FAMILIES, NOT_TRACKED_MIN_ZERO_DAYS,
                         _consecutive_zero_scrape_days, _scrape_daily_series,
                         _scrape_lookup, curves, existing_editions,
                         get_event_end_date, meta, ratios, summary, tournaments_out)


    add_historical_editions(EXCLUDE_FAMILIES, curves, daily,
                            get_event_date, summary, tournaments_out)

    tournaments_out = finalize_cards(completed_tids, prod_model,
                                     tournaments_out)


    # ── Data linking validation ──────────────────────────────────────────────
    # Compare scrape counts to website output. Flag any tournament where the
    # scrape has entries but the website shows 0 — that's a linking failure.
    if os.path.exists(scrape_path):
        def _edition(t):
            return canonicalize_family(t['family']), t.get('year')

        open_cards = [t for t in tournaments_out if is_open_season(t.get('year'))]
        all_open = {_edition(t): t['current_count'] for t in open_cards}
        live_open = {_edition(t): t['current_count'] for t in open_cards if t.get('status') == 'live'}
        # Tournaments that are intentionally excluded (completed, blitz, WO sub-events, etc.)
        excluded_families = {canonicalize_family(f) for f in EXCLUDE_FAMILIES}
        settled = {_edition(t) for t in open_cards if t.get('status') in ('complete', 'in_progress')}
        link_warnings = []
        for (fam, yr), counts in _scrape_lookup.items():
            if not is_open_season(yr):
                continue
            key = (canonicalize_family(fam), yr)
            if key[0] in excluded_families or key in settled:
                continue
            scrape_count = counts['net']
            if scrape_count > 0 and live_open.get(key) == 0:
                link_warnings.append(f"  ⚠ {fam} {yr}: scrape={scrape_count}, website=0")
            elif scrape_count > 0 and key not in all_open:
                link_warnings.append(f"  ⚠ {fam} {yr}: scrape={scrape_count}, NOT IN OUTPUT")
        if link_warnings:
            print(f"\n{'!'*60}")
            print(f"  DATA LINKING WARNINGS — {len(link_warnings)} tournaments with scrape data not reflected in output:")
            for w in link_warnings:
                print(w)
            print(f"{'!'*60}")
        else:
            print("\n✓ Data linking check passed: all scraped tournaments reflected in output")
