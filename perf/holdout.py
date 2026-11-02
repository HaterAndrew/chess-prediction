"""The sealed test: what the frozen model published for events after the freeze.

The method froze on FROZEN_ON, when its last change was judged on the
walk-forward (#191); FROZEN_HASH is shared.model_version.model_hash() of
that code. Events starting after FROZEN_ON never informed a choice about the
model, so the forecasts the frozen code published for them are graded apart
from the rest of the live record. tests/test_holdout.py fails when a model
source changes. A display-only change may add a verified equivalent source
hash to FROZEN_HASHES, retaining the original forecasts. If any forecast moves,
the test is no longer sealed: start a new freeze on the day the change merges.
"""
import pandas as pd

from perf.live_record import summarize_live

FROZEN_ON = '2026-09-27'
FROZEN_HASH = 'e0e6631e4c8e940d'
# Chart-only scrape tails (2026-11-02): all 412 cards' forecast fields and all
# 1,086 walk-forward rows remained identical. Keep the original cohort too.
FROZEN_HASHES = frozenset({FROZEN_HASH, 'e2b539beaa9c6f75'})


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
