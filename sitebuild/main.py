"""04d orchestrator: load, fit, cards, metadata, history, output.

Fitting and forecasting live in forecast/, the scrape merge in
sitebuild.scrape_merge, and the two card loops in sitebuild.cards and
sitebuild.metadata; the rest is the functionized 04d body.
"""
import os

import pandas as pd

from pipeline_utils import is_event_complete
from tournament_aliases import canonicalize_family
from shared.season import CURRENT_SEASON, is_open_season

from forecast import fit_models
from sitebuild.assemble import finalize_cards
from sitebuild.cards import build_model_cards
from sitebuild.helpers import (OUTPUT_DIR, TODAY, _fam_eq, determine_status,
                               m04c, print_recalibration)
from sitebuild.history import add_historical_editions
from sitebuild.metadata import build_metadata_cards
from sitebuild.scrape_join import (consecutive_zero_scrape_days, counts_by_edition,
                                   latest_by_edition, scrape_daily_series)
from sitebuild.scrape_merge import (inject_scrape_curves, merge_scrape_counts,
                                    normalize_scrape)


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
    scrape_path = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
    if os.path.exists(scrape_path):
        scrape = normalize_scrape(pd.read_csv(scrape_path), default_year=CURRENT_SEASON)
        latest_scrape = latest_by_edition(scrape)
        updated = merge_scrape_counts(summary, latest_scrape)
        # Reanchor ALL daily T values from last_reg to event_start so the model
        # trains and predicts in a consistent coordinate system (T=0 = event start).
        daily = m04c.reanchor_daily_to_event_start(summary, daily, meta)
        daily = inject_scrape_curves(scrape, summary, daily, meta, pd.Timestamp.now())
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

    # The nowcast model (recalibrated), the ratio model and the template
    # curves. Completed 2026 tournaments fold into training (rolling retrain).
    fitted = fit_models(summary, daily, enrichment_lookup, completed_tids)
    print_recalibration(fitted.recal)

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

    build_model_cards(fitted, daily, determine_status, get_event_date,
                      get_event_end_date, meta, summary,
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
                         _scrape_lookup, fitted, existing_editions,
                         get_event_end_date, meta, summary, tournaments_out)


    add_historical_editions(EXCLUDE_FAMILIES, fitted.curves, daily,
                            get_event_date, summary, tournaments_out)

    tournaments_out = finalize_cards(completed_tids, fitted.model,
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
