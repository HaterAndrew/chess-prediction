"""The sealed test grades only what the frozen model published after the freeze,
and any change to the model's sources is caught before it can unseal it."""
import pandas as pd

from perf.holdout import FROZEN_HASH, FROZEN_HASHES, FROZEN_ON, holdout_block, sealed
from perf.evaluation_periods import CURRENT_FROZEN_HASH
from perf.live_record import last_run_per_day, match_forecasts
from shared.model_version import model_hash


def _rec(forecast_date, T, model_hash=FROZEN_HASH, final=100, point=100):
    return {'season': 2026, 'tid': 1, 'family': 'Harbor Open', 'T': T,
            'forecast_date': forecast_date, 'as_of_date': forecast_date,
            'point': point, 'low': point - 10, 'high': point + 10, 'final': final,
            'log_error': 0.0, 'in_range': 1, 'route': 'model', 'model_hash': model_hash}


def test_only_events_starting_after_the_freeze_by_the_frozen_code():
    after = _rec('2026-10-01', 14)             # starts 2026-10-15
    straddles = _rec('2026-09-20', 14)         # starts 2026-10-04: after the freeze
    before = _rec('2026-09-10', 14)            # starts 2026-09-24
    other_code = _rec('2026-10-01', 14, model_hash='0' * 16)
    assert sealed([after, straddles, before, other_code]) == [after, straddles]


def test_the_block_names_the_freeze_and_scores_like_the_live_record():
    block = holdout_block([_rec('2026-10-01', 14)], '2026-03-23', '2026-10-01')
    assert (block['frozen_on'], block['model_hash'], block['n_records']) == \
        (FROZEN_ON, FROZEN_HASH, 1)
    assert block['pooled']['14']['n'] == 1
    assert holdout_block([], '2026-03-23', '2026-10-01')['n_records'] == 0


def test_the_model_is_frozen():
    assert model_hash() == CURRENT_FROZEN_HASH, (
        "A model source changed after the current freeze (perf/evaluation_periods.py). "
        "Review forecast equivalence or start a new period; preserve the original archive.")
    assert CURRENT_FROZEN_HASH not in FROZEN_HASHES


def test_equivalent_display_sources_keep_old_and_new_forecasts():
    records = [_rec('2026-10-01', 14, model_hash=h) for h in sorted(FROZEN_HASHES)]
    assert sealed(records) == records
    assert holdout_block(records, '2026-10-01', '2026-10-01')['model_hashes'] == sorted(FROZEN_HASHES)
    assert sealed(records, frozen_hash='custom-freeze') == []
    custom = _rec('2026-10-01', 14, model_hash='custom-freeze')
    assert sealed([*records, custom], frozen_hash='custom-freeze') == [custom]


def test_same_day_equivalent_versions_are_matched_once_before_holdout_grading():
    equivalent = next(h for h in FROZEN_HASHES if h != FROZEN_HASH)
    row = {'family': 'Harbor Open', 'year': 2026, 'as_of_date': '2026-10-01',
           'origin': 'nightly', 'published': 1, 'point': 100, 'ci_lower': 90,
           'ci_upper': 110, 'route': 'model'}
    ledger = pd.DataFrame([
        {**row, 'run_ts': '2026-10-01 01:00', 'model_hash': FROZEN_HASH},
        {**row, 'run_ts': '2026-10-01 02:00', 'model_hash': equivalent},
    ])
    events = pd.DataFrame([{'tid': 1, 'family': 'Harbor Open', 'tournament_year': 2026,
                            'start': pd.Timestamp('2026-10-15'), 'final_count': 100}])
    records = match_forecasts(last_run_per_day(ledger), events, horizons=[14])
    assert len(records) == len(sealed(records)) == 1
    assert records[0]['model_hash'] == equivalent
