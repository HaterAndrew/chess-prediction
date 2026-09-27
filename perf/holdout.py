"""The sealed test: what the frozen model published for events after the freeze.

The method froze on FROZEN_ON, when its last change was judged on the
walk-forward (#191); FROZEN_HASH is shared.model_version.model_hash() of
that code. Events starting after FROZEN_ON never informed a choice about the
model, so the forecasts the frozen code published for them are graded apart
from the rest of the live record. tests/test_holdout.py fails when a model
source changes: if every forecast stays the same, update FROZEN_HASH alone;
if any moves, the test is no longer sealed, so move FROZEN_ON to the day the
change merges as well.
"""
import pandas as pd

from perf.live_record import summarize_live

FROZEN_ON = '2026-09-27'
FROZEN_HASH = '6b0bd39145d00730'


def sealed(records, frozen_on=FROZEN_ON, frozen_hash=FROZEN_HASH):
    """Live-record rows the frozen code published for events starting after the freeze."""
    after = pd.Timestamp(frozen_on)
    return [r for r in records
            if r['model_hash'] == frozen_hash
            and pd.Timestamp(r['forecast_date']) + pd.Timedelta(days=int(r['T'])) > after]


def holdout_block(records, first_date, last_date):
    """The sealed test's scores, in the live record's shape, with the freeze named."""
    block = summarize_live(sealed(records), first_date, last_date)
    return {'frozen_on': FROZEN_ON, 'model_hash': FROZEN_HASH, **block}
