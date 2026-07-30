"""Dev demo main() (04c 2250-2330, verbatim; hardcoded Chicago Open)."""

import json
import os
from datetime import datetime

from model.blind_test import run_blind_test
from model.constants import CHOP_POINTS, OUTPUT_DIR, TODAY
from model.core import N5v4_Final
from model.curves import build_template_curves
from model.data_io import load_data, load_meta_lookup
from model.legacy_site import build_website_json
from model.stats import lognormal_ci

def main():
    print("Loading data...")
    # load_data returns 4 values (summary, daily, meta, hist); the old
    # 3-tuple unpack crashed main() on entry (v5 chore — every other caller
    # already unpacked 4).
    summary, daily, meta, _hist = load_data()
    meta_lookup = load_meta_lookup(meta)

    # Fit model on all completed data
    print("Fitting N5v4 model...")
    model = N5v4_Final()
    model.fit(summary, daily)

    # Show Chicago Open ratios (the fix)
    print("\n" + "=" * 70)
    print("CHICAGO OPEN RATIO ANALYSIS (after excluding 2026 in-progress)")
    print("=" * 70)
    chi_rats = model.ratios.get('Chicago Open', {})
    for T in CHOP_POINTS:
        rats = chi_rats.get(T, [])
        if rats:
            vals = [r[0] for r in rats]
            yrs = [int(r[1]) for r in rats]
            med, lo, hi = lognormal_ci(vals)
            print(f"  T-{T:<4}  n={len(vals)}  ratios=[{', '.join(f'{v:.2f}' for v in vals)}]")
            print(f"         years={yrs}  median={med:.2f}  lognormal 80% CI=[{lo:.2f}, {hi:.2f}]")

    # Chicago Open 2026 prediction
    print("\n" + "=" * 70)
    print("2026 CHICAGO OPEN PREDICTION")
    print("=" * 70)
    # Event: May 21-25. T = days to event_start (no duration offset needed).
    current = 179
    days_to_start = (datetime(2026, 5, 21) - TODAY).days
    pred, lo, hi = model.predict_nowcast(current, days_to_start, 'Chicago Open')
    print(f"\n  Current registrations:  {current}")
    print(f"  Days to event start:    {days_to_start}")
    print(f"  Point estimate:         {pred}")
    print(f"  80% CI:                 [{lo}, {hi}]")
    print(f"  CI width:               {hi - lo}")
    print("  Historical range:       860-960 (2022-2025)")

    print(f"\n  N5v4 (fixed):            pred={pred}  CI=[{lo}, {hi}]  width={hi-lo}")

    # Blind validation
    print("\n")
    run_blind_test(summary, daily)

    # Build template curves
    print("\nBuilding template curves...")
    template_curves = build_template_curves(summary, daily)

    # Build website JSON
    print("\n" + "=" * 70)
    print("BUILDING WEBSITE JSON")
    print("=" * 70)
    website_data = build_website_json(summary, daily, meta_lookup, model, template_curves)

    outpath = os.path.join(OUTPUT_DIR, "website_data.json")
    with open(outpath, 'w') as f:
        json.dump(website_data, f, indent=2, default=str)

    print(f"\nSaved to {outpath}")
    print(f"Total tournaments: {len(website_data['tournaments'])}")

    statuses = {}
    for t in website_data['tournaments']:
        statuses[t['status']] = statuses.get(t['status'], 0) + 1
    print(f"By status: {statuses}")

    print("\nKey live tournament predictions:")
    for t in website_data['tournaments']:
        if t['status'] == 'live' and t['current_count'] >= 5:
            print(f"  {t['family']:<45} cnt={t['current_count']:>5}  "
                  f"pred={t['point_estimate']:>5}  "
                  f"CI=[{t['ci_lower']}, {t['ci_upper']}]  T-{t['days_remaining']}")

    print(f"\n{'=' * 70}")
    print("DONE")
    print(f"{'=' * 70}")

