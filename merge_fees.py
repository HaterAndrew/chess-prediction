"""
merge_fees.py — Populate tournament_metadata.csv fee columns from the scraped
chesstour fee flyers in tournament_fees.csv.

scrape_fees.py writes tournament_fees.csv keyed by chesstour flyer CODE
(ho26, dco26, wo26, ...). The prediction path (04d_website_data_v2.py) reads
fees from tournament_metadata.csv keyed by FAMILY. Nothing bridged the two, so
fees scraped weeks ago never reached the cards — the data-health scan flagged
seven near-events with null fees that are sitting in tournament_fees.csv right
now. This joins them via validate_fees.FAMILY_TO_CODE.

Safe by construction:
  - only fills fee columns that are currently null (never overwrites),
  - cross-checks the flyer's event_start against the metadata start_date
    (±3 days) so a wrong code mapping can't paste fees onto the wrong event,
  - skips a flyer whose regular_fee > onsite_fee or is out of [1, 2000]
    (an inverted/garbled parse, e.g. the DC International 825/200 row) and
    emits a WARNING: line so the gap stays visible instead of poisoning a card,
  - respects the early-bird guardrails: an EB fee is copied only when present
    and not demoted (eb_demoted_reason empty).

Usage:
    python3 merge_fees.py            # merge, write metadata
    python3 merge_fees.py --dry-run  # report what would change, write nothing

MANUAL-ONLY (H7): this is NOT wired into the daily/weekly GitHub Actions
pipeline. Fees only reach the cards when a human runs scrape_fees.py and then
this. If fee columns look stale on near-events, that is expected until someone
re-runs both by hand.
"""

import os
import sys

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
from validate_fees import FAMILY_TO_CODE  # noqa: E402
from tournament_aliases import canonicalize_family  # noqa: E402

OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
FEES_CSV = os.path.join(OUTPUT_DIR, "tournament_fees.csv")
META_CSV = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")

YEAR = 2026
YY = str(YEAR)[2:]
FEE_MAX = 2000  # upper sanity bound on a single entry fee


def _num(v):
    return float(v) if pd.notna(v) and str(v).strip() != "" else None


def _code_for(family):
    return FAMILY_TO_CODE.get(family) or FAMILY_TO_CODE.get(canonicalize_family(family))


def merge_fees(dry_run=False):
    if not os.path.exists(FEES_CSV) or not os.path.exists(META_CSV):
        print(f"WARNING: fee-merge skipped — missing {FEES_CSV} or {META_CSV}")
        return 0

    fees = pd.read_csv(FEES_CSV)
    fees = fees[fees["year"] == YEAR]
    meta = pd.read_csv(META_CSV)

    filled = 0
    skipped = 0
    for idx, row in meta[meta["year"] == YEAR].iterrows():
        family = row["family"]
        if pd.notna(row.get("regular_fee")):
            continue  # already has a fee — never overwrite
        code = _code_for(family)
        if not code:
            continue
        match = fees[fees["url"].astype(str).str.contains(f"/{code}{YY}.", regex=False)]
        if len(match) == 0:
            continue
        fr = match.iloc[0]

        # Cross-check the event date so a stray code can't paste fees onto the
        # wrong tournament. If either date is unparseable/missing we CANNOT verify
        # the match, so skip rather than merge blind (H3: was `except: pass`, which
        # silently merged on any parse failure — the exact case the guard exists for).
        try:
            md = pd.to_datetime(row["start_date"])
            fd = pd.to_datetime(fr["event_start"])
        except Exception:
            md = fd = pd.NaT
        if pd.isna(md) or pd.isna(fd):
            print(f"WARNING: fee-merge skipped {family}: cannot verify flyer {code}{YY} "
                  f"date (metadata={row.get('start_date')!r}, flyer={fr.get('event_start')!r})")
            skipped += 1
            continue
        if abs((md - fd).days) > 3:
            print(f"WARNING: fee-merge skipped {family}: flyer {code}{YY} date "
                  f"{fd.date()} != metadata {md.date()} (>3d)")
            skipped += 1
            continue

        reg, ons, eb = _num(fr.get("regular_fee")), _num(fr.get("onsite_fee")), _num(fr.get("early_bird_fee"))
        if reg is None and ons is None:
            continue
        # Sanity guard: inverted or out-of-range fee = suspect parse, do not merge.
        if reg is not None and (reg < 1 or reg > FEE_MAX):
            print(f"WARNING: fee-merge skipped {family}: regular_fee {reg} out of range ({code}{YY})")
            skipped += 1
            continue
        if reg is not None and ons is not None and reg > ons:
            print(f"WARNING: fee-merge skipped {family}: regular_fee {reg} > onsite_fee {ons} "
                  f"— suspect flyer parse ({code}{YY})")
            skipped += 1
            continue

        if not dry_run:
            if reg is not None:
                meta.at[idx, "regular_fee"] = reg
            if ons is not None:
                meta.at[idx, "onsite_fee"] = ons
            eb_demoted = str(fr.get("eb_demoted_reason") or "").strip()
            if eb is not None and not eb_demoted:
                meta.at[idx, "early_bird_fee"] = eb
                ebd = fr.get("early_bird_deadline")
                if pd.notna(ebd) and str(ebd).strip():
                    meta.at[idx, "early_bird_deadline"] = str(ebd)[:10]
        print(f"  {'(dry) ' if dry_run else ''}filled {family}: regular={reg} onsite={ons} eb={eb} ({code}{YY})")
        filled += 1

    if not dry_run and filled:
        meta.to_csv(META_CSV, index=False)
    print(f"\nFee merge: {filled} families filled, {skipped} skipped (suspect/mismatched), "
          f"{'DRY RUN — metadata unchanged' if dry_run else 'metadata written'}")
    return filled


if __name__ == "__main__":
    merge_fees(dry_run="--dry-run" in sys.argv[1:])
