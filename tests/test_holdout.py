"""The sealed test grades only what the frozen model published after the freeze,
and any change to the model's sources is caught before it can unseal it."""
from perf.holdout import FROZEN_HASH, FROZEN_ON, holdout_block, sealed
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
    assert model_hash() == FROZEN_HASH, (
        "A model source changed after the freeze (perf/holdout.py). If every forecast "
        "is unchanged, update FROZEN_HASH alone; if any moved, the sealed test is over: "
        "move FROZEN_ON to the day the change merges as well.")
