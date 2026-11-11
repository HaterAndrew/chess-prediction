"""Evaluation ownership and the published original results survive later changes."""
import json

import pandas as pd
import pytest

from perf import evaluation_periods as periods
from perf import live_run
from perf.holdout import FROZEN_HASH
from pipeline.ledger import LEDGER_FIELDS

ORIGINAL = {'archived_on': '2026-11-10', 'results': {'n_records': 16, 'model_hash': FROZEN_HASH}}


def _row(model_hash, *, stamp='2026-11-11 12:00:00', day='2026-11-11', point=100):
    return {'family': 'Harbor Open', 'year': 2026, 'as_of_date': day,
            'run_ts': stamp, 'origin': 'nightly', 'published': 1,
            'point': point, 'ci_lower': 90 if point is not None else None,
            'ci_upper': 110 if point is not None else None,
            'route': 'model' if point is not None else 'insufficient_history',
            'model_hash': model_hash}


def _events(final=100):
    return pd.DataFrame([{'tid': 1, 'family': 'Harbor Open', 'tournament_year': 2026,
                          'start': pd.Timestamp('2026-11-25'), 'final_count': final}])


def test_a_later_old_version_cannot_replace_the_current_period_forecast():
    ledger = pd.DataFrame([_row(periods.CURRENT_FROZEN_HASH),
                           _row(FROZEN_HASH, stamp='2026-11-11 20:00:00', point=900)])
    current = periods.evaluation_blocks(ledger, _events(), ORIGINAL)[1]['results']
    assert current['n_records'] == 1
    assert current['pooled']['14']['mae_pct'] == 0
    assert current['eras'][0]['model_hash'] == periods.CURRENT_FROZEN_HASH


def test_current_hash_before_the_new_period_is_not_retrospective_evidence():
    ledger = pd.DataFrame([_row(periods.CURRENT_FROZEN_HASH, day='2026-11-09')])
    current = periods.evaluation_blocks(ledger, _events(), ORIGINAL)[1]['results']
    assert current['n_records'] == 0
    assert current['protocol']['first_date'] is None
    assert current['frozen_on'] == periods.CURRENT_FROZEN_ON


def test_current_unavailability_blocks_an_older_day_and_counts_the_omission():
    ledger = pd.DataFrame([_row(periods.CURRENT_FROZEN_HASH, day='2026-11-12', point=None),
                           _row(periods.CURRENT_FROZEN_HASH)])
    events = _events()
    events['start'] = pd.Timestamp('2026-11-26')
    current = periods.evaluation_blocks(ledger, events, ORIGINAL)[1]['results']
    assert current['n_records'] == 0
    assert current['n_unavailable_forecasts'] == 1
    assert current['n_invalid_ranges'] == 0


def test_original_results_do_not_follow_mutable_current_truth():
    ledger = pd.DataFrame([_row(periods.CURRENT_FROZEN_HASH)])
    before = periods.evaluation_blocks(ledger, _events(100), ORIGINAL)[0]
    after = periods.evaluation_blocks(ledger, _events(900), ORIGINAL)[0]
    assert before == after
    archive = periods.load_original_evaluation()
    assert before['results'] == ORIGINAL['results']
    assert len(archive['records']) == before['results']['n_records'] == 16
    assert before['results']['model_hash'] == FROZEN_HASH
    assert archive['source_commit'] == '3067563d23987a55c577254dcc6d68238c598478'


def test_missing_and_corrupt_archives_fail_loudly(tmp_path):
    path = tmp_path / 'archive.json'
    with pytest.raises(FileNotFoundError):
        periods.load_original_evaluation(path)
    path.write_bytes(periods.ORIGINAL_ARCHIVE.read_bytes() + b' ')
    with pytest.raises(ValueError, match='integrity check failed'):
        periods.load_original_evaluation(path)


@pytest.mark.parametrize('header_only', [False, True])
def test_missing_or_header_only_ledgers_keep_original_and_waiting_periods(tmp_path, monkeypatch, header_only):
    if header_only:
        for name in live_run.LEDGER_FILES:
            pd.DataFrame(columns=LEDGER_FIELDS).to_csv(tmp_path / name, index=False)
    monkeypatch.setattr(live_run, 'finished_events', lambda *_: _events())
    block = live_run.live_record_block(None, pd.Timestamp('2026-11-10'), str(tmp_path))
    assert block['n_records'] == 0
    assert block['holdout']['n_records'] == 16
    assert block['evaluation_periods'][1]['results']['n_records'] == 0
    assert block['evaluation_periods'][1]['results']['frozen_on'] == periods.CURRENT_FROZEN_ON
    assert json.dumps(block, allow_nan=False)
