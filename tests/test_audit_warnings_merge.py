"""audit_warnings.json has two writers: the nightly pipeline and the weekly
enrichment run. Each used to overwrite the file, so the enrichment run erased
the nightly warnings (2026-10-03: 4 warnings became 0) until the next night.
Each writer now replaces only the steps it owns and keeps the rest."""
import json

import pytest

from pipeline import config, warns


NIGHTLY = {'step': 'Refresh tournament summary', 'text': 'export missing', 'count': 1,
           'generated': '2026-10-03 06:34:57'}
FEES = {'step': 'Enrichment: fees', 'text': 'flyer parse failed', 'count': 2,
        'generated': '2026-09-28 12:10:00'}


def _owns_fees(step):
    return step == 'Enrichment: fees'


def test_enrichment_keeps_the_nightly_entries():
    previous = {'generated': '2026-10-03 06:34:57', 'warnings': [NIGHTLY]}
    out = warns.merge_warnings(previous, [], _owns_fees, '2026-10-03 19:12:00')
    assert out['warnings'] == [NIGHTLY]
    assert out['count'] == 1 and out['total_occurrences'] == 1
    assert out['generated'] == '2026-10-03 19:12:00'


def test_a_step_that_ran_clean_drops_its_old_entries():
    previous = {'generated': 'x', 'warnings': [NIGHTLY, FEES]}
    out = warns.merge_warnings(previous, [], _owns_fees, 'now')
    assert [w['step'] for w in out['warnings']] == ['Refresh tournament summary']


def test_fresh_entries_come_first_and_carry_this_run_time():
    previous = {'generated': 'x', 'warnings': [NIGHTLY]}
    current = [{'step': 'Enrichment: fees', 'text': 'a'},
               {'step': 'Enrichment: fees', 'text': 'a'}]
    out = warns.merge_warnings(previous, current, _owns_fees, 'now')
    assert out['warnings'][0] == {'step': 'Enrichment: fees', 'text': 'a', 'count': 2,
                                  'generated': 'now'}
    assert out['count'] == 2
    assert out['total_occurrences'] == 3


def test_kept_entries_from_the_old_format_inherit_the_file_time():
    legacy = {'step': 'Validate scraped data', 'text': 'w', 'count': 1}
    previous = {'generated': '2026-10-03 06:34:57', 'warnings': [legacy]}
    out = warns.merge_warnings(previous, [], _owns_fees, 'now')
    assert out['warnings'][0]['generated'] == '2026-10-03 06:34:57'


def test_nightly_owns_every_step_except_enrichment():
    assert warns.nightly_owns('PIPELINE FAILURE')
    assert warns.nightly_owns('Validate scraped data')
    assert not warns.nightly_owns('Enrichment: standings')


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    out, site = tmp_path / 'output', tmp_path / 'docs'
    out.mkdir()
    site.mkdir()
    monkeypatch.setattr(config, 'OUTPUT_DIR', str(out))
    monkeypatch.setattr(config, 'SITE_DIR', str(site))
    monkeypatch.setattr(config, 'RUN_TS', '2026-10-04 01:20:00')
    monkeypatch.setattr(warns, '_PIPELINE_WARNINGS', [])
    return out, site


def test_nightly_write_keeps_enrichment_entries_in_both_copies(dirs):
    out, site = dirs
    (out / 'audit_warnings.json').write_text(json.dumps(
        {'generated': 'old', 'count': 2, 'total_occurrences': 3, 'warnings': [NIGHTLY, FEES]}))
    warns._PIPELINE_WARNINGS.append({'step': 'Validate scraped data', 'text': 'new'})
    warns.write_audit_warnings()
    for path in (out / 'audit_warnings.json', site / 'audit_warnings.json'):
        data = json.loads(path.read_text())
        assert [w['step'] for w in data['warnings']] == ['Validate scraped data', 'Enrichment: fees']
        assert data['count'] == 2


@pytest.mark.parametrize('previous', ['{not json', '["a list"]', '{"warnings": "x"}'])
def test_an_unreadable_previous_file_becomes_a_warning_in_the_new_one(dirs, previous):
    """Overwriting it loses the other writer's entries; the loss must show
    where operators look, not only in a log line."""
    out, _ = dirs
    (out / 'audit_warnings.json').write_text(previous)
    warns.write_audit_warnings()
    data = json.loads((out / 'audit_warnings.json').read_text())
    assert data['count'] == 1
    assert data['warnings'][0]['step'] == warns.AUDIT_FILE_STEP
    assert 'could not read the previous' in data['warnings'][0]['text']
