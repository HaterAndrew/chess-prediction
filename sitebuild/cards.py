"""Model-path card loop (04d main() body, verbatim).

Callables that were sibling closures (status/event-date helpers) arrive
as parameters, so their bindings to main()-scope state are preserved.
tournaments_out is mutated in place, as before.
"""
import pandas as pd

from pipeline_utils import (apply_plausibility_clamp, build_chart_series,
                            chart_series_start_date, roster_pending_model_ok)
from prediction_window import registration_close_date, window_decayed_estimate
from ratio_model import predict_with_lognormal_ci
from tournament_aliases import canonicalize_family

from sitebuild.helpers import (TODAY, _apply_wo_top6_adjustment,
                               _fam_eq, m04c, sanitize_early_bird)


def build_model_cards(curves, daily, determine_status, get_event_date, get_event_end_date, meta, prod_model, ratios, summary, t2026, tournaments_out, withdrawal_lookup):
    for _, row in t2026.iterrows():
        family = row['family']
        tid = row['tid']
        current_count = row['final_count']

        # Skip tiny sub-events and low-value entries
        if current_count < 1:
            continue
        # Skip completed tournaments with very few registrations (likely sub-events or data issues)
        # Expand family aliases so renamed tournaments (e.g. DC Open ↔ Philadelphia Open) find their history
        hist_families = [family]
        if hasattr(m04c, 'FAMILY_ALIASES') and family in m04c.FAMILY_ALIASES:
            hist_families.extend(m04c.FAMILY_ALIASES[family])
        hist_check = summary[
            (summary['family'].isin(hist_families)) &
            (~summary['is_online'].fillna(False)) &
            (~summary['is_covid'].fillna(False)) &
            (summary['tournament_year'] < 2026) &
            (summary['tournament_year'] >= 2019)
        ]
        if current_count < 10 and len(hist_check) == 0:
            continue

        event_date = get_event_date(family, 2026)
        event_end_date = get_event_end_date(family, 2026)
        registration_close = registration_close_date(event_date, event_end_date)
        status = determine_status(row, event_date, event_end_date, registration_close)

        # Two horizons. days_to_start drives the ratio model (training is anchored
        # to event_start). days_to_close is the online-registration horizon — for
        # multi-schedule events that runs days past event_start. days_into_window /
        # window_len locate TODAY inside the post-start registration window.
        if event_date is not None:
            days_to_start = max((event_date - TODAY).days, 0)
            days_into_window = max((TODAY - pd.Timestamp(event_date)).days, 0)
        else:
            days_to_start = 60
            days_into_window = 0
        if event_date is not None and registration_close is not None:
            days_to_close = max((registration_close - TODAY).days, 0)
            window_len = max((registration_close - pd.Timestamp(event_date)).days, 0)
        else:
            days_to_close = days_to_start
            window_len = 0

        # Displayed countdown: days to event_start before the event, then days to
        # registration close once the event is underway (entries still arriving).
        days_remaining = days_to_start if days_to_start > 0 else days_to_close

        # Registration curve (template) — also feeds the roster-pending gate below.
        curve = curves.get(family, curves.get('__global__', {}))

        # v5 Cat R: roster-pending rows ride the model path only when the same
        # pace gate the interim path uses says the live curve is trustworthy;
        # otherwise fall through to the metadata loop (metadata_pace /
        # metadata_historical_avg / settled), exactly as before admission.
        is_roster_pending = bool(row['roster_pending']) if 'roster_pending' in row.index else False
        if is_roster_pending and not roster_pending_model_ok(
                current_count, days_to_start, status, event_date, curve):
            continue

        # Exclude tournaments too far out — predictions are meaningless with 1-3 registrants
        if days_to_start > 250:
            continue

        # Get metadata
        m = meta[_fam_eq(meta['family'], family) & (meta['year'] == 2026)]
        eb_deadline = m.iloc[0]['early_bird_deadline'] if len(m) > 0 and pd.notna(m.iloc[0].get('early_bird_deadline')) else None
        eb_fee = float(m.iloc[0]['early_bird_fee']) if len(m) > 0 and pd.notna(m.iloc[0].get('early_bird_fee')) else None
        reg_fee = float(m.iloc[0]['regular_fee']) if len(m) > 0 and pd.notna(m.iloc[0].get('regular_fee')) else None
        onsite_fee = float(m.iloc[0]['onsite_fee']) if len(m) > 0 and pd.notna(m.iloc[0].get('onsite_fee')) else None
        # Anchor the EB gap check to THIS card's event date, not a stale event_start
        # left over from an earlier loop (H14). Matches the sibling call below.
        eb_deadline, eb_fee = sanitize_early_bird(family, 2026, eb_deadline, eb_fee, reg_fee,
                                                  event_date.strftime('%Y-%m-%d') if event_date else None)

        # Historical data (needed for guardrails and output)
        # Include alias families for tournaments with no direct history
        families_to_search = [family]
        if hasattr(m04c, 'FAMILY_ALIASES') and family in m04c.FAMILY_ALIASES:
            families_to_search.extend(m04c.FAMILY_ALIASES[family])
        hist = summary[
            (summary['family'].isin(families_to_search)) &
            (~summary['is_online'].fillna(False)) &
            (~summary['is_covid'].fillna(False)) &
            (summary['tournament_year'] < 2026) &
            (summary['tournament_year'] >= 2019)
        ].sort_values('tournament_year')
        historical = _apply_wo_top6_adjustment(family, [
            {"year": int(h['tournament_year']), "count": int(h['final_count']),
             "family": h['family']}
            for _, h in hist.iterrows()
        ])

        # Predictions — use production model with guardrails
        hist_counts = [h['count'] for h in historical]
        prediction_source = 'model'
        if status == 'complete':
            point, ci_lo, ci_hi = current_count, current_count, current_count
            prediction_source = 'final'
        elif status == 'in_progress':
            # Online registration has closed (the 2-day schedule, the last entry
            # point, has started) — pass through the scraped count directly.
            # Does NOT include on-site/walk-up registrations (online pre-reg only).
            point, ci_lo, ci_hi = current_count, current_count, current_count
            prediction_source = 'live_scrape'
        elif status == 'live' and days_remaining > 0:
            if days_to_start == 0 and window_len > 0:
                # Post-start online-registration window: the 5-day schedule has
                # begun but 4/3/2-day online entries are still arriving. Take the
                # event-start (T=0) ratio bucket — the full count-at-start -> final
                # multiplier — and decay it toward 1.0 as registration close nears.
                # build_ratio_model's `ratios` carry a real T=0 bucket;
                # prod_model.predict_nowcast's finest bucket is T-1, so at T=0 it
                # would over-extrapolate from a one-day-earlier ratio.
                p0, lo0, hi0 = predict_with_lognormal_ci(
                    current_count, 0, family, ratios)
                point, ci_lo, ci_hi = window_decayed_estimate(
                    current_count, p0, lo0, hi0, days_into_window, window_len)
                prediction_source = 'model_online_window'
            else:
                point, ci_lo, ci_hi = prod_model.predict_nowcast(
                    current_count, days_to_start, family,
                    early_bird_deadline=eb_deadline,
                    event_start_date=event_date)
                if point is None:
                    point, ci_lo, ci_hi = predict_with_lognormal_ci(
                        current_count, days_to_start, family, ratios)

            # Plausibility check: if the point estimate is far outside the family's
            # historical range, blend toward the historical median while preserving
            # the model's CI width. Floors the result at current_count so a published
            # final can never sit below the entries already scraped (v3 N2).
            point, ci_lo, ci_hi = apply_plausibility_clamp(
                point, ci_lo, ci_hi, current_count, hist_counts, days_remaining)
        else:
            point, ci_lo, ci_hi = current_count, current_count, current_count

        # Daily data for chart. build_chart_series (pipeline_utils) dedupes per T,
        # converts to day_from_start, warns (never rescales) on A4 anomalies, and
        # drops non-increasing points. See v3 N1 / audit/AUDIT_2026-07-25.md.
        daily_data = build_chart_series(
            tid, daily, current_count,
            is_live=status in ('live', 'in_progress'))
        # Calendar date of the day_from_start==0 point, so the front end can date
        # every chart point from its own index value instead of counting array
        # positions back from the generation date (v3 P1).
        daily_start_date = chart_series_start_date(tid, daily, event_date)

        # Registration curve (template) — `curve` computed above the gate.
        reg_curve = []
        for db in [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]:
            pct = curve.get(db, 0)
            reg_curve.append({"days_before": db, "cumulative_pct": round(float(pct), 4)})

        # Canonicalize family name so live and historical rows agree on form
        # (CCA emits "World Open, lower sections" with comma; canonical is the
        # no-comma form per tournament_aliases.FAMILY_GROUPS). Without this the
        # chart's histLookup and alerts.py's at-T comparator can't match the
        # 2026 live row against its 2023-2025 historical editions.
        display_family = canonicalize_family(family)

        # YoY pacing context: what was the count at the same T last year?
        prior_year_pace = None
        if status == 'live' and days_remaining > 0:
            # Find most recent prior year's tournament for this family
            _fam_mask = _fam_eq(summary['family'], family)
            prior_hist = summary[
                _fam_mask &
                (summary['tournament_year'] == summary[
                    _fam_mask &
                    (summary['tournament_year'] < 2026)
                ]['tournament_year'].max())
            ]
            if len(prior_hist) > 0:
                prior_tid = prior_hist.iloc[0]['tid']
                prior_daily = daily[daily['tid'] == prior_tid]
                if len(prior_daily) > 0:
                    # Find prior count at the same days-to-event-start point
                    # (prior_daily T is event_start-anchored, so compare against
                    # days_to_start, not days_remaining which counts to reg close).
                    prior_at_T = prior_daily[prior_daily['T'] >= days_to_start].sort_values('T')
                    if len(prior_at_T) > 0:
                        prior_count_at_T = int(prior_at_T.iloc[0]['cum_regs'])
                        prior_year_val = int(prior_hist.iloc[0]['tournament_year'])
                        prior_year_pace = {
                            "year": prior_year_val,
                            "count_at_same_point": prior_count_at_T,
                            "final": int(prior_hist.iloc[0]['final_count']),
                        }

        # Withdrawal data from scrape (lookup is keyed canonical)
        wd_info = withdrawal_lookup.get(canonicalize_family(family), {})
        withdrawal_count = wd_info.get('withdrawal_count', 0)
        gross_count = wd_info.get('gross_count', int(current_count))

        # AUDIT.md C8 / B1 — surface model confidence + tier on each prediction.
        # Count direct editions PLUS alias-family editions so a renamed/relocated
        # family (e.g. "DC International", whose history lives under "Philadelphia
        # International") reports its true edition count instead of 0 and isn't
        # wrongly flagged low-confidence. Mirrors the alias sum 04c uses for CI
        # widening; without it the JSON field under-reports for every alias family.
        if hasattr(prod_model, 'family_n_editions'):
            n_editions_for_family = prod_model.family_n_editions.get(family, 0)
            for _alias in m04c.FAMILY_ALIASES.get(family, []):
                n_editions_for_family += prod_model.family_n_editions.get(_alias, 0)
        else:
            n_editions_for_family = 0
        low_confidence = n_editions_for_family < 4
        # prod_model._last_tier only describes a predict_nowcast() call. The
        # online-window path uses predict_with_lognormal_ci instead, so leave the
        # tier null there rather than reporting a stale value from another row.
        tier_used = (getattr(prod_model, '_last_tier', None)
                     if status == 'live' and prediction_source != 'model_online_window'
                     else None)

        t_out = {
            "family": display_family,
            "year": 2026,
            "event_start": event_date.strftime('%Y-%m-%d') if event_date else None,
            "event_end": None,
            "registration_close": (registration_close.strftime('%Y-%m-%d')
                                   if registration_close is not None else None),
            "early_bird_deadline": str(eb_deadline)[:10] if eb_deadline and str(eb_deadline) != 'nan' else None,
            "early_bird_fee": eb_fee,
            "regular_fee": reg_fee,
            "onsite_fee": onsite_fee,
            "current_count": int(current_count),
            "gross_count": int(gross_count),
            "withdrawal_count": int(withdrawal_count),
            "days_remaining": int(days_remaining),
            "point_estimate": int(point),
            "ci_lower": int(ci_lo),
            "ci_upper": int(ci_hi),
            "ci_level": 0.80,
            "historical": historical,
            "daily_data": daily_data,
            "daily_start_date": daily_start_date,
            "registration_curve": reg_curve,
            "status": 'live' if status == 'in_progress' else status,
            "prediction_source": prediction_source,
            "prior_year_pace": prior_year_pace,
            "low_confidence": low_confidence,
            "n_historical_editions": n_editions_for_family,
            # v5 Cat R: an admitted roster-pending row keeps its disclosure — the
            # badge string app.js already maps — even though the estimate is now
            # model output rather than the old interim card.
            "prediction_tier": 'roster-pending' if is_roster_pending else tier_used,
        }

        # Add event_end from metadata
        if len(m) > 0 and pd.notna(m.iloc[0].get('end_date')):
            t_out['event_end'] = str(m.iloc[0]['end_date'])[:10]

        tournaments_out.append(t_out)
