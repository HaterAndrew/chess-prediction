"""The original sealed-test selector, retained for its original source hashes.

The method froze on FROZEN_ON after walk-forward evaluation (#191).
FROZEN_HASHES contains that method and its verified equivalent source versions.
Its published results are now archived in perf/evaluations/2026-09-27.json.
This selector remains available for reproducing the original cohort.

The separate active period and fixed source hash live in perf.evaluation_periods;
tests/test_holdout.py detects changes to that frozen source. A policy that moves
a forecast starts a new period on its merge day, preserving prior results and
ledger rows. Never add that changed policy's hash to this original hash set.
"""
import pandas as pd

from perf.live_record import summarize_live

FROZEN_ON = '2026-09-27'
FROZEN_HASH = 'e0e6631e4c8e940d'
# Chart-only scrape tails (2026-11-02): all 412 cards' forecast fields and all
# 1,086 walk-forward rows remained identical. Keep the original cohort too.
# Coverage/chart cutoff repair: all 412 baseline forecasts are identical on
# the same inputs, and all 11 original sealed predictions remain intact.
# The separately recorded November 2 observations change inputs and outcomes.
FROZEN_HASHES = frozenset({FROZEN_HASH, 'e2b539beaa9c6f75', '598f8e1fe4fd334a'})


def sealed(records, frozen_on=FROZEN_ON, frozen_hash=FROZEN_HASH):
    """Live-record rows the frozen code published for events starting after the freeze."""
    after = pd.Timestamp(frozen_on)
    accepted = FROZEN_HASHES if frozen_hash == FROZEN_HASH else {frozen_hash}
    return [r for r in records
            if r['model_hash'] in accepted
            and pd.Timestamp(r['forecast_date']) + pd.Timedelta(days=int(r['T'])) > after]


def holdout_block(records, first_date, last_date):
    """The sealed test's scores, in the live record's shape, with the freeze named."""
    block = summarize_live(sealed(records), first_date, last_date)
    return {'frozen_on': FROZEN_ON, 'model_hash': FROZEN_HASH,
            'model_hashes': sorted(FROZEN_HASHES), **block}
