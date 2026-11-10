"""The published original results and the separate current evaluation period."""
import hashlib
import json
from pathlib import Path

import pandas as pd

from perf.live_record import last_run_per_day, match_forecasts, summarize_live

CURRENT_FROZEN_ON = '2026-11-10'
CURRENT_FROZEN_HASH = '1cc6cfdc8bacadab'
ORIGINAL_ARCHIVE = Path(__file__).with_name('evaluations') / '2026-09-27.json'
ORIGINAL_ARCHIVE_SHA256 = '2f12ab79058a86dd61e879a04bbfa51b115a7d1e02741480d0b1fc000b667665'


def load_original_evaluation(path=None):
    """Refuse a missing or changed archive rather than recomputing old results."""
    raw = (ORIGINAL_ARCHIVE if path is None else Path(path)).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_ARCHIVE_SHA256:
        raise ValueError('Original evaluation archive integrity check failed')
    return json.loads(raw)


def evaluation_blocks(ledger, events, original):
    """Select current-version publications before daily/horizon matching."""
    after = pd.Timestamp(CURRENT_FROZEN_ON)
    selected = ledger[(ledger['model_hash'] == CURRENT_FROZEN_HASH)
                      & (pd.to_datetime(ledger['as_of_date']) >= after)]
    runs = last_run_per_day(selected)
    unavailable = []
    records = match_forecasts(runs, events[events['start'] > after], unavailable=unavailable)
    first = runs['as_of'].min().strftime('%Y-%m-%d') if not runs.empty else None
    last = runs['as_of'].max().strftime('%Y-%m-%d') if not runs.empty else None
    current = {'frozen_on': CURRENT_FROZEN_ON, 'model_hash': CURRENT_FROZEN_HASH,
               'model_hashes': [CURRENT_FROZEN_HASH], 'n_unavailable_forecasts': len(unavailable),
               **summarize_live(records, first, last)}
    return [
        {'label': 'Original evaluation', 'state': 'archived',
         'archived_on': original['archived_on'], 'results': original['results']},
        {'label': 'Current evaluation', 'state': 'active', 'results': current},
    ]
