"""04d orchestrator: load, fit, cards, metadata, history, output.

The two big loops live in sitebuild.cards / sitebuild.metadata; the rest
is the functionized 04d body verbatim.
"""
import os

import pandas as pd

from pipeline_utils import is_event_complete
from ratio_model import build_ratio_model
from tournament_aliases import canonicalize_family

from sitebuild.assemble import finalize_cards
from sitebuild.cards import build_model_cards
from sitebuild.curves import build_template_curves
from sitebuild.helpers import (OUTPUT_DIR, TODAY, _fam_eq, determine_status,
                               m04c)
from sitebuild.history import add_historical_editions
from sitebuild.metadata import build_metadata_cards


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

    # Merge fresh scrape data into summary for 2026 tournaments
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
        # Get the most recent scrape per tournament
        latest_scrape = scrape.sort_values('date').groupby('tournament_name').last().reset_index()
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
            # Match by family name (strip year prefix "2026 " from scrape name)
            scrape_name = s['tournament_name']
            family_name = scrape_name.replace('2026 ', '', 1) if scrape_name.startswith('2026 ') else scrape_name
            mask = _fam_eq(summary['family'], family_name) & (summary['tournament_year'] == 2026)
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
            scrape_name = s['tournament_name']
            family_name = scrape_name.replace('2026 ', '', 1) if scrape_name.startswith('2026 ') else scrape_name
            tid_match = summary[_fam_eq(summary['family'], family_name) & (summary['tournament_year'] == 2026)]
            if len(tid_match) == 0:
                continue
            tid = tid_match.iloc[0]['tid']
            last_reg = tid_match.iloc[0].get('last_reg')
            meta_row = meta[_fam_eq(meta['family'], family_name) & (meta['year'] == 2026)]
            if len(meta_row) == 0:
                meta_row = meta[(meta['year'] == 2026) & (meta['start_date'] > pd.Timestamp.now())]
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
        (summary['tournament_year'] == 2026) &
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
        end_dt = get_event_end_date(family, 2026)
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
        n_2026 = len(recal_data[recal_data['tournament_year'] == 2026])
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

    # Get 2026 tournaments
    t2026 = summary[
        (summary['tournament_year'] == 2026) &
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

    print(f"Found {len(t2026)} 2026 tournaments (after filtering)")

    # Build withdrawal lookup from latest scrape data (family -> withdrawal_count).
    # Keyed on the CANONICAL family so comma/whitespace variants between the
    # scraper's spelling and summary rows still match (v5 Cat R).
    withdrawal_lookup = {}
    if os.path.exists(scrape_path):
        for _, s in latest_scrape.iterrows():
            scrape_name = s['tournament_name']
            fam = scrape_name.replace('2026 ', '', 1) if scrape_name.startswith('2026 ') else scrape_name
            wd = int(s.get('withdrawal_count', 0)) if pd.notna(s.get('withdrawal_count')) else 0
            gross = int(s.get('entry_count', 0))
            withdrawal_lookup[canonicalize_family(fam)] = {'withdrawal_count': wd, 'gross_count': gross}

    tournaments_out = []

    build_model_cards(curves, daily, determine_status, get_event_date,
                      get_event_end_date, meta, prod_model, ratios, summary,
                      t2026, tournaments_out, withdrawal_lookup)


    # Add tournaments from metadata that have no registrations yet
    # Build scrape lookup so metadata-only tournaments can pick up live entry counts
    _scrape_lookup = {}
    if os.path.exists(scrape_path):
        for _, s in latest_scrape.iterrows():
            sn = s['tournament_name']
            fam = sn.replace('2026 ', '', 1) if sn.startswith('2026 ') else sn
            net = int(s['active_count']) if pd.notna(s['active_count']) and s['active_count'] > 0 else int(s['entry_count'])
            gross = int(s.get('entry_count', 0))
            wd = int(s.get('withdrawal_count', 0)) if pd.notna(s.get('withdrawal_count')) else 0
            _scrape_lookup[fam] = {'net': net, 'gross': gross, 'wd': wd}

    # Consecutive scrape days at 0 entries before a near-event card is relabelled
    # not_tracked (v3 N8). One zero is a scrape hiccup; several in a row is a real
    # cancellation.
    NOT_TRACKED_MIN_ZERO_DAYS = 3


    def _consecutive_zero_scrape_days(family_name):
        """How many of the most recent consecutive scrape days show 0 entries.

        Returns a large number when the family has never been scraped at all, since
        "no scrape rows ever" is genuinely untracked rather than a transient miss.
        """
        if not os.path.exists(scrape_path):
            return NOT_TRACKED_MIN_ZERO_DAYS

        def _strip_year(n):
            return n[5:] if isinstance(n, str) and n.startswith('2026 ') else n

        ev = scrape[scrape['tournament_name'].apply(_strip_year) == family_name]
        if len(ev) == 0:
            return NOT_TRACKED_MIN_ZERO_DAYS

        by_day = {}
        for _, r in ev.iterrows():
            cnt = int(r['active_count']) if pd.notna(r.get('active_count')) and r['active_count'] > 0 else int(r['entry_count'])
            day = pd.to_datetime(r['date']).normalize()
            by_day[day] = max(by_day.get(day, 0), cnt)

        streak = 0
        for day in sorted(by_day, reverse=True):
            if by_day[day] == 0:
                streak += 1
            else:
                break
        return streak


    def _scrape_daily_series(family_name, fallback_count):
        """Real [day_index, cumulative_count] entry-bar history for a 2026 event,
        read straight from daily_scrape.csv and matched by family name. Mirrors the
        main path's cummax cleaning. Falls back to a single point only when fewer
        than two scrapes exist — the chart needs >=3 points to draw bars, so the old
        hardcoded [[0, count]] rendered nothing for these events.

        Returns (series, start_date) where start_date is the 'YYYY-MM-DD' calendar
        date of day 0, or None when unknown. v3 P1: the front end dates every chart
        point from this anchor plus the point's own day index, so a gap in scraping
        can no longer shift the labels. v3 N9: this path now runs the same
        max-vs-count invariant as build_chart_series instead of going unchecked.
        """
        if not os.path.exists(scrape_path):
            return [[0, int(fallback_count)]], None

        def _strip_year(n):
            return n[5:] if isinstance(n, str) and n.startswith('2026 ') else n

        ev = scrape[scrape['tournament_name'].apply(_strip_year) == family_name].sort_values('date')
        if len(ev) < 2:
            return [[0, int(fallback_count)]], None
        by_day = {}
        min_date = ev['date'].min()
        for _, r in ev.iterrows():
            cnt = int(r['active_count']) if pd.notna(r.get('active_count')) and r['active_count'] > 0 else int(r['entry_count'])
            day = int((r['date'] - min_date).days)
            by_day[day] = max(by_day.get(day, 0), cnt)
        peak, series = 0, []
        for day in sorted(by_day):
            peak = max(peak, by_day[day])
            series.append([day, peak])

        # v3 N9: same post-build invariant the main path enforces. This series is
        # built from the scrape itself so it should never exceed the scraped count;
        # if it does, the family-name match pulled in another event's rows.
        if series and fallback_count and max(p[1] for p in series) > int(fallback_count):
            print(f"WARNING: roster-pending series max ({max(p[1] for p in series)}) "
                  f"exceeds count ({int(fallback_count)}) for {family_name}; "
                  f"check the family-name match.")

        start_date = pd.to_datetime(min_date).strftime('%Y-%m-%d')
        return series, start_date


    # Canonical-aware so a metadata event ("... (in Connecticut)") isn't re-added
    # when the main path already emitted its folded form ("Eastern Class
    # Championships") once a fresh export pulls it into the roster.
    existing_families = {canonicalize_family(t['family']) for t in tournaments_out}
    build_metadata_cards(EXCLUDE_FAMILIES, NOT_TRACKED_MIN_ZERO_DAYS,
                         _consecutive_zero_scrape_days, _scrape_daily_series,
                         _scrape_lookup, curves, existing_families, meta,
                         ratios, summary, tournaments_out)


    add_historical_editions(EXCLUDE_FAMILIES, curves, daily,
                            get_event_date, summary, tournaments_out)

    tournaments_out = finalize_cards(completed_tids, prod_model,
                                     tournaments_out)


    # ── Data linking validation ──────────────────────────────────────────────
    # Compare scrape counts to website output. Flag any tournament where the
    # scrape has entries but the website shows 0 — that's a linking failure.
    if os.path.exists(scrape_path):
        all_2026 = {canonicalize_family(t['family']): t['current_count'] for t in tournaments_out if t.get('year') == 2026}
        live_2026 = {canonicalize_family(t['family']): t['current_count'] for t in tournaments_out if t.get('year') == 2026 and t.get('status') == 'live'}
        # Tournaments that are intentionally excluded (completed, blitz, WO sub-events, etc.)
        excluded_or_complete = {canonicalize_family(f) for f in EXCLUDE_FAMILIES}
        excluded_or_complete.update(canonicalize_family(t['family']) for t in tournaments_out if t.get('year') == 2026 and t.get('status') in ('complete', 'in_progress'))
        link_warnings = []
        for _, s in latest_scrape.iterrows():
            sn = s['tournament_name']
            fam = sn.replace('2026 ', '', 1) if sn.startswith('2026 ') else sn
            fam_canon = canonicalize_family(fam)
            if fam_canon in excluded_or_complete:
                continue
            scrape_count = int(s['active_count']) if pd.notna(s['active_count']) and s['active_count'] > 0 else int(s['entry_count'])
            if scrape_count > 0 and fam_canon in live_2026 and live_2026[fam_canon] == 0:
                link_warnings.append(f"  ⚠ {fam}: scrape={scrape_count}, website=0")
            elif scrape_count > 0 and fam_canon not in all_2026:
                link_warnings.append(f"  ⚠ {fam}: scrape={scrape_count}, NOT IN OUTPUT")
        if link_warnings:
            print(f"\n{'!'*60}")
            print(f"  DATA LINKING WARNINGS — {len(link_warnings)} tournaments with scrape data not reflected in output:")
            for w in link_warnings:
                print(w)
            print(f"{'!'*60}")
        else:
            print("\n✓ Data linking check passed: all scraped tournaments reflected in output")
