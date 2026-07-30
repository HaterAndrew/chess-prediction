"""Metadata/interim card loop (04d main() body, verbatim)."""
import numpy as np
import pandas as pd

from pipeline_utils import (pace_gate_ok)
from ratio_model import predict_with_lognormal_ci
from tournament_aliases import canonicalize_family

from sitebuild.helpers import (TODAY, _apply_wo_top6_adjustment,
                               m04c, sanitize_early_bird)


def build_metadata_cards(EXCLUDE_FAMILIES, NOT_TRACKED_MIN_ZERO_DAYS, _consecutive_zero_scrape_days, _scrape_daily_series, _scrape_lookup, curves, existing_families, meta, ratios, summary, tournaments_out):
    for _, mrow in meta[meta['year'] == 2026].iterrows():
        mfamily = mrow['family']
        if canonicalize_family(mfamily) in existing_families or mfamily in EXCLUDE_FAMILIES:
            continue
        event_date = pd.to_datetime(mrow['start_date'])
        event_end = pd.to_datetime(mrow['end_date']) if pd.notna(mrow.get('end_date')) else event_date
        days_remaining = (event_date - TODAY).days
        # Far-future metadata (registration not meaningfully open yet) — skip.
        if days_remaining > 300:
            continue
        # Pick up live entry count from scrape data if available.
        #
        # Gross, not net. H13 settled on one published count semantic — the gross
        # row count — so the cards, the performance tab, the freshness guard and
        # 04e's grading all quote the same number. This path was missed when that
        # was applied and kept reading net, so two cards (Central California Open
        # 25 vs 27, Southern Open 200 vs 206) published a different semantic from
        # every other card on the page. Nothing surfaced it until data_health's
        # stale-count rule was corrected to compare gross against gross.
        #
        # The withdrawal figures stay available below as their own fields; they are
        # a separate fact, not a competing version of this one.
        scrape_info = _scrape_lookup.get(mfamily, {})
        gross_count = scrape_info.get('gross', 0) or scrape_info.get('net', 0)
        current_count = gross_count
        withdrawal_count = scrape_info.get('wd', 0)
        # Historical data. Canonicalize first so a relocated edition ("... (in
        # Connecticut)") and CCA name variants ("World Open Under 13 Championship")
        # match their historical series via FAMILY_GROUPS/aliases instead of reading
        # as a brand-new family with zero history.
        canon_family = canonicalize_family(mfamily)
        _aliases = getattr(m04c, 'FAMILY_ALIASES', {})
        hist_families = list(dict.fromkeys(
            [mfamily, canon_family]
            + _aliases.get(mfamily, [])
            + _aliases.get(canon_family, [])
        ))
        hist = summary[
            (summary['family'].isin(hist_families)) &
            (~summary['is_online'].fillna(False)) &
            (~summary['is_covid'].fillna(False)) &
            (summary['tournament_year'] < 2026) &
            (summary['tournament_year'] >= 2019)
        ].sort_values('tournament_year')
        historical = _apply_wo_top6_adjustment(mfamily, [
            {"year": int(h['tournament_year']), "count": int(h['final_count']),
             "family": h['family']}
            for _, h in hist.iterrows()
        ])
        # H12: an event whose start date has already passed but that never entered
        # the roster path (a CCA sub-class the export folds into its parent — e.g.
        # World Open Under 13) used to be silently dropped by an
        # `event_date <= TODAY: continue` above. If live scrape counts exist, emit a
        # settled (event over) or in-progress (event running) card from the observed
        # count instead of losing the event. The point estimate is the observed
        # count, never a projection — we have no roster/model for it.
        if event_date <= TODAY:
            settled_count = current_count if current_count > 0 else gross_count
            if settled_count <= 0:
                # No roster and no live signal — nothing truthful to display.
                continue
            ended = event_end < TODAY
            curve = curves.get(mfamily, curves.get('__global__', {}))
            reg_curve = [{"days_before": db,
                          "cumulative_pct": round(float(curve.get(db, 0)), 4)}
                         for db in [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]]
            eb_deadline = mrow.get('early_bird_deadline')
            eb_fee = float(mrow['early_bird_fee']) if pd.notna(mrow.get('early_bird_fee')) else None
            reg_fee = float(mrow['regular_fee']) if pd.notna(mrow.get('regular_fee')) else None
            onsite_fee = float(mrow['onsite_fee']) if pd.notna(mrow.get('onsite_fee')) else None
            _eb_dl_norm = str(eb_deadline)[:10] if pd.notna(eb_deadline) and str(eb_deadline) != 'nan' else None
            _eb_dl_norm, eb_fee = sanitize_early_bird(
                mfamily, 2026, _eb_dl_norm, eb_fee, reg_fee, event_date.strftime('%Y-%m-%d'))
            _rp_series, _rp_start = _scrape_daily_series(mfamily, settled_count)
            t_out = {
                "family": mfamily,
                "year": 2026,
                "event_start": event_date.strftime('%Y-%m-%d'),
                "event_end": str(mrow['end_date'])[:10] if pd.notna(mrow.get('end_date')) else None,
                "early_bird_deadline": _eb_dl_norm,
                "early_bird_fee": eb_fee,
                "regular_fee": reg_fee,
                "onsite_fee": onsite_fee,
                "current_count": int(settled_count),
                "gross_count": int(gross_count) if gross_count > 0 else int(settled_count),
                "withdrawal_count": int(withdrawal_count),
                "days_remaining": 0 if ended else max((event_end - TODAY).days, 0),
                "point_estimate": int(settled_count),
                "ci_lower": int(settled_count),
                "ci_upper": int(settled_count),
                "ci_level": 0.80,
                "historical": historical,
                "daily_data": _rp_series,
                "daily_start_date": _rp_start,
                "registration_curve": reg_curve,
                "status": "complete" if ended else "live",
                "n_historical_editions": len(historical),
                "low_confidence": True,
                "prediction_tier": "roster-pending",
                "prediction_source": "settled_actual" if ended else "in_progress_actual",
            }
            tournaments_out.append(t_out)
            print(f"  Added {'settled' if ended else 'in-progress'} from metadata: "
                  f"{mfamily} (event {event_date.strftime('%Y-%m-%d')}, entries={settled_count})")
            continue
        # This event isn't in the trained model roster yet (registration opened
        # after the last all_registrations.csv export). Until a fresh export pulls
        # it into the main path, give an INTERIM estimate that still tracks live
        # registrations instead of a frozen historical average, and flag it
        # low-confidence so the card discloses the degraded mode.
        hist_counts = [h['count'] for h in historical]
        hist_mean = np.mean(hist_counts) if hist_counts else 100
        # Sanity check: 0 registrations close to event = likely cancelled/not tracked.
        #
        # v3 N8 (audit/AUDIT_2026-07-25.md): this is the same missing-scrape-day
        # failure class as the incident. A single scrape returning 0 for a live event
        # is indistinguishable here from a genuinely untracked one, and the card
        # silently disappeared from the live list. Require the zero to persist across
        # several consecutive scrape days before relabelling, and say so out loud
        # when it happens — a real cancellation stays at zero, a scrape hiccup does not.
        if days_remaining < 30 and current_count == 0:
            zero_days = _consecutive_zero_scrape_days(mfamily)
            if zero_days >= NOT_TRACKED_MIN_ZERO_DAYS:
                status_label = "not_tracked"
                print(f"WARNING: relabelling {mfamily} as not_tracked — 0 entries "
                      f"across {zero_days} consecutive scrape day(s), {days_remaining} "
                      f"day(s) out.")
            else:
                # Not enough evidence to call it untracked; keep it live.
                status_label = "live"
                print(f"WARNING: {mfamily} scraped 0 entries {days_remaining} day(s) "
                      f"out but only {zero_days} consecutive zero-day(s) "
                      f"(need {NOT_TRACKED_MIN_ZERO_DAYS}); keeping it live.")
        else:
            status_label = "live"

        days_to_start = max((pd.Timestamp(event_date) - TODAY).days, 0)
        prediction_source = "metadata_historical_avg"
        # Only extrapolate from live pace when the signal is informative: close to
        # the event AND enough registrations that 1-2 early sign-ups don't get
        # multiplied into an absurd projection (a 1-registrant event 170 days out
        # has no usable pace). Otherwise lean on the historical average — still
        # flagged low-confidence below.
        # v4 X1: the bare 90-day gate routed 46-90 day cards into the clamp
        # ceiling (the curve share out there is ~1-2%, so the ratio scale-up was
        # noise labeled as pace). pace_gate_ok keeps the old 45-day behaviour and
        # grants the extension only where the family curve carries signal.
        curve = curves.get(mfamily, curves.get('__global__', {}))
        pace_usable = pace_gate_ok(current_count, days_to_start, curve)
        if hist_counts and pace_usable and status_label == "live":
            # Resolve the name the ratio model trained under (summary uses
            # 01_data_prep's canonical form, which can differ from the FAMILY_GROUPS
            # head — e.g. "World Open Under 13"); else predict falls to global ratios.
            ratio_family = canon_family
            for cand in hist_families:
                if cand in ratios:
                    ratio_family = cand
                    break
            p, lo, hi = predict_with_lognormal_ci(
                current_count, days_to_start, ratio_family, ratios)
            # Clamp into a sane band around observed history so a sparse, far-out
            # count can't produce an absurd interim number.
            lo_band, hi_band = min(hist_counts) * 0.6, max(hist_counts) * 1.5
            point_estimate = int(min(max(p, lo_band), hi_band))
            ci_lo = int(min(max(lo, lo_band), hi_band))
            ci_hi = int(min(max(hi, lo_band), hi_band))
            if ci_hi <= ci_lo:
                ci_lo, ci_hi = int(min(hist_counts)), int(max(hist_counts))
            prediction_source = "metadata_pace"
        else:
            point_estimate = int(hist_mean)
            # Variance-based CI from history when no live pace signal is usable.
            if len(hist_counts) >= 5:
                ci_lo = int(np.percentile(hist_counts, 10))
                ci_hi = int(np.percentile(hist_counts, 90))
            elif len(hist_counts) >= 2:
                ci_lo = int(min(hist_counts))
                ci_hi = int(max(hist_counts))
            else:
                ci_lo = int(hist_mean * 0.7)
                ci_hi = int(hist_mean * 1.3)
        reg_curve = []
        for db in [120, 90, 75, 60, 42, 28, 21, 14, 7, 3, 1, 0]:
            pct = curve.get(db, 0)
            reg_curve.append({"days_before": db, "cumulative_pct": round(float(pct), 4)})
        eb_deadline = mrow.get('early_bird_deadline')
        eb_fee = float(mrow['early_bird_fee']) if pd.notna(mrow.get('early_bird_fee')) else None
        reg_fee = float(mrow['regular_fee']) if pd.notna(mrow.get('regular_fee')) else None
        onsite_fee = float(mrow['onsite_fee']) if pd.notna(mrow.get('onsite_fee')) else None
        _eb_dl_norm = str(eb_deadline)[:10] if pd.notna(eb_deadline) and str(eb_deadline) != 'nan' else None
        _eb_dl_norm, eb_fee = sanitize_early_bird(mfamily, 2026, _eb_dl_norm, eb_fee, reg_fee, event_date.strftime('%Y-%m-%d'))
        _rp_series, _rp_start = _scrape_daily_series(mfamily, current_count)
        t_out = {
            "family": mfamily,
            "year": 2026,
            "event_start": event_date.strftime('%Y-%m-%d'),
            "event_end": str(mrow['end_date'])[:10] if pd.notna(mrow.get('end_date')) else None,
            "early_bird_deadline": _eb_dl_norm,
            "early_bird_fee": eb_fee,
            "regular_fee": reg_fee,
            "onsite_fee": onsite_fee,
            "current_count": int(current_count),
            "gross_count": int(gross_count),
            "withdrawal_count": int(withdrawal_count),
            "days_remaining": int(days_remaining),
            "point_estimate": point_estimate,
            "ci_lower": ci_lo,
            "ci_upper": ci_hi,
            "ci_level": 0.80,
            "historical": historical,
            "daily_data": _rp_series,
            "daily_start_date": _rp_start,
            "registration_curve": reg_curve,
            "status": status_label,
            # Interim roster-fallback disclosure (see estimate logic above).
            "n_historical_editions": len(hist_counts),
            "low_confidence": True,
            "prediction_tier": "roster-pending",
            "prediction_source": prediction_source,
        }
        tournaments_out.append(t_out)
        print(f"  Added from metadata: {mfamily} (event {event_date.strftime('%Y-%m-%d')}, "
              f"{days_remaining} days out, entries={current_count}, est={point_estimate} "
              f"[{prediction_source}], status={status_label})")
