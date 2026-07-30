"""Dedupe, walk-in multiplier, sort, and website_data.json write
(04d main() tail, verbatim). Returns the deduplicated tournaments_out --
the original rebound the local; the caller rebinds from the return value.
"""
import json
import os

import pandas as pd

from tournament_aliases import canonicalize_family

from sitebuild.helpers import OUTPUT_DIR, TODAY, m04c


def finalize_cards(completed_tids, prod_model, tournaments_out):
    # ── Deduplicate tournaments with variant names (e.g. comma vs no comma) ──
    seen_keys = {}
    deduped = []
    for t_out in tournaments_out:
        # Canonicalize so comma variants AND venue-suffix variants ("... (in
        # Connecticut)") collapse to one key — not just comma/case normalization,
        # which let a relocated edition coexist with its folded form.
        key = (canonicalize_family(t_out["family"]), t_out["year"])
        if key in seen_keys:
            # Keep the one with more data (higher current_count)
            existing = seen_keys[key]
            if t_out["current_count"] > existing["current_count"]:
                deduped.remove(existing)
                seen_keys[key] = t_out
                deduped.append(t_out)
        else:
            seen_keys[key] = t_out
            deduped.append(t_out)
    if len(tournaments_out) != len(deduped):
        print(f"\nDeduplication: {len(tournaments_out)} -> {len(deduped)} tournaments")
    tournaments_out = deduped

    # ── Apply walk-in multiplier — only for completed tournaments (after event start) ──
    # (P3a) duplicate importlib import removed — reuse the module-level m04c
    _m04c = m04c
    _walkin_mults = _m04c.load_walkin_multipliers()
    _walkin_applied = 0
    _walkin_by_source = {'family': 0, 'type': 0, 'estimate': 0, 'none': 0}
    for t_out in tournaments_out:
        # Only apply walk-in estimates after the event has started
        if t_out["status"] in ("live", "not_tracked"):
            continue
        family = t_out["family"]
        tp, tl, th, ratio, wsource = _m04c.apply_walkin_multiplier(
            t_out["point_estimate"], t_out["ci_lower"], t_out["ci_upper"],
            family, _walkin_mults)
        if ratio:
            t_out["walkin_multiplier"] = round(ratio, 3)
            t_out["walkin_source"] = wsource
            t_out["total_estimate"] = tp
            t_out["total_ci_lower"] = tl
            t_out["total_ci_upper"] = th
            _walkin_applied += 1
            _walkin_by_source[wsource] = _walkin_by_source.get(wsource, 0) + 1
    print(f"\nWalk-in multiplier applied to {_walkin_applied} completed/historical tournaments")
    print(f"  by source: {_walkin_by_source}")
    # Loud warning if family-specific data is missing for nearly all events.
    # Without walk_in_family_stats.csv the entire system silently degrades to the
    # global estimate path — see AUDIT.md A1/B2.
    _total_with_source = sum(_walkin_by_source.values())
    if _total_with_source > 0:
        _est_pct = _walkin_by_source['estimate'] / _total_with_source
        if _est_pct > 0.5:
            print(f"  WARNING: {_est_pct:.0%} of walk-in multipliers used 'estimate' fallback. "
                  f"Confirm output/walk_in_family_stats.csv exists and is fresh.")

    # Sort: live first (by days_remaining desc), then 2026 complete, then historical
    status_order = {'live': 0, 'complete': 1, 'historical': 2, 'unknown': 3}
    tournaments_out.sort(key=lambda t: (status_order.get(t['status'], 9), t['days_remaining']))

    # Count by status
    n_live = sum(1 for t in tournaments_out if t['status'] == 'live')
    n_complete = sum(1 for t in tournaments_out if t['status'] == 'complete')
    n_historical = sum(1 for t in tournaments_out if t['status'] == 'historical')

    # K2: walk-in provenance computed at build time. The old string hardcoded
    # "94 tournament-years, 24 families, MAPE 6.9%" — the actual stats file carries
    # different counts and no MAPE is ever computed for the walk-in leg, so the MAPE
    # was unverifiable. State the real family/year coverage and drop the MAPE.
    _wi_stats_path = os.path.join(OUTPUT_DIR, "walk_in_family_stats.csv")
    if os.path.exists(_wi_stats_path):
        _wi = pd.read_csv(_wi_stats_path)
        _walkin_prov = f"{int(_wi['n_years'].sum())} family-years across {len(_wi)} families"
    else:
        _walkin_prov = "family-level historical standings-to-prereg ratios"

    output = {
        "generated": TODAY.strftime('%Y-%m-%d'),
        "generated_time": pd.Timestamp.now(tz='America/New_York').isoformat(),
        "model": "N5v4_Final",
        "model_description": ("Ensemble model (N5v4): historical ratio (harmonic mean) + per-family pooled Huber regression (final ~ count_at_T + T). T anchored to event_start. T-dependent weights (ratio: 0.80 at T<=3, 0.55 at T<=7, 0.30 at T<=28, 0.15 at T>28). 80% CI from lognormal prediction intervals, LOO-calibrated with T-dependent shrinkage. Rolling retraining on completed 2026 tournaments. Automated bias + CI recalibration. Walk-in multiplier: post-hoc adjustment using historical standings-to-prereg ratios (" + _walkin_prov + ")."),
        "n_completed_in_training": len(completed_tids) if completed_tids else 0,
        "tournaments": tournaments_out
    }

    # Print summary
    print(f"\nGenerated {len(tournaments_out)} tournaments ({n_live} live, {n_complete} complete 2026, {n_historical} historical)")

    # AUDIT.md B1 — surface prediction-tier distribution so silent fallback is visible
    if hasattr(prod_model, '_tier_counts'):
        tier_counts = dict(prod_model._tier_counts)
        total = sum(tier_counts.values())
        if total > 0:
            print(f"\nPrediction tier distribution (n={total}):")
            for tier, count in sorted(tier_counts.items(), key=lambda kv: -kv[1]):
                print(f"  {tier:<22} {count:>4}  ({100*count/total:>4.1f}%)")
            size_matched = tier_counts.get('size-matched', 0) + tier_counts.get('guard-no-ratios', 0)
            if total > 0 and size_matched / total > 0.20:
                print(f"  WARNING: {100*size_matched/total:.0f}% of predictions used size-matched fallback "
                      f"or had no ratios. Family coverage is degraded.")
    for t in tournaments_out:
        ci = f"[{t['ci_lower']}, {t['ci_upper']}]"
        print(f"  {t['status']:12s} {t['family']:45s}  yr={t['year']}  count={t['current_count']:>5}  pred={t['point_estimate']:>5}  CI={ci:>15}  days={t['days_remaining']:>3}")

    # Save
    out_path = os.path.join(OUTPUT_DIR, "website_data.json")
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")
    return tournaments_out
