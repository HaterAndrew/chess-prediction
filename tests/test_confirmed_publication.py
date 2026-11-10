"""Publication failure cannot create gradeable rows; producer identity survives."""
import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from pipeline import confirmed_publication as confirmed, deploy_hook as deploy
from pipeline.ledger import append_ledger, ledger_rows


def candidate(root, *, source_hash='0123456789abcdef'):
    asset = json.dumps({'generated': '2026-11-10', 'is_stale': False, 'tournaments': [
        {'family': 'Example Open', 'year': 2026, 'status': 'live', 'current_count': 5,
         'point_estimate': 10, 'ci_lower': 7, 'ci_upper': 13, 'event_start': '2026-11-24'}]}).encode()
    rows = ledger_rows(json.loads(asset), run_ts='2026-11-10 12:00:00', model_label='n5v7',
                       model_hash=source_hash, code_commit='producer1234', origin='nightly')
    root.mkdir(exist_ok=True)
    value = {'schema': 1, 'asset_sha256': hashlib.sha256(asset).hexdigest(),
             'run_ts': rows[0]['run_ts'], 'model_label': 'n5v7', 'model_hash': source_hash,
             'code_commit': 'producer1234', 'rows': rows}
    (root / 'forecast_candidate.json').write_text(json.dumps(value))
    append_ledger([{**rows[0], 'model_hash': 'legacy'}], root / 'forecast_ledger.csv')
    return asset, value


def test_confirmed_deployment_appends_producer_stamped_rows_once_preserving_old_bytes(tmp_path):
    asset, _ = candidate(tmp_path)
    path = tmp_path / 'forecast_ledger.csv'
    before = path.read_bytes()
    assert confirmed.record_confirmed(asset, tmp_path) == 1
    assert path.read_bytes().startswith(before)
    rows = list(csv.DictReader(path.open()))
    assert rows[-1]['model_hash'] == '0123456789abcdef'
    assert rows[-1]['code_commit'] == 'producer1234'
    assert rows[-1]['published'] == '1'
    after = path.read_bytes()
    assert confirmed.record_confirmed(asset, tmp_path) == 0
    assert path.read_bytes() == after
    assert (tmp_path / 'checksums.json').is_file()


def test_unmatched_candidate_is_refused_without_ledger_mutation(tmp_path):
    asset, value = candidate(tmp_path)
    path = tmp_path / 'forecast_ledger.csv'
    before = path.read_bytes()
    value['rows'][0]['point'] = 999
    (tmp_path / 'forecast_candidate.json').write_text(json.dumps(value))
    with pytest.raises(ValueError, match='does_not_match'):
        confirmed.record_confirmed(asset, tmp_path)
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match='digest_mismatch'):
        confirmed.record_confirmed(b'{"is_stale":false}', tmp_path)
    assert confirmed.record_confirmed(b'{"is_stale":true}', tmp_path) == 0
    assert path.read_bytes() == before


def test_successful_upstream_candidate_with_failed_live_publication_never_enters_ledger(tmp_path, monkeypatch):
    asset, _ = candidate(tmp_path / 'output')
    path = tmp_path / 'output/forecast_ledger.csv'
    before = path.read_bytes()
    (tmp_path / 'docs/data').mkdir(parents=True)
    (tmp_path / 'docs/data/website_data.json').write_bytes(asset)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CLOUDFLARE_DEPLOY_HOOK',
                       'https://api.cloudflare.com/client/v4/workers/builds/deploy_hooks/synthetic-hook-identifier')
    monkeypatch.setattr(deploy, 'request_build', Mock(return_value='accepted'))
    monkeypatch.setattr(deploy, 'wait_for_asset', Mock(side_effect=deploy.DeployError('not_published')))
    assert deploy.main() == 1
    assert path.read_bytes() == before
    assert not (tmp_path / 'output/forecast_publications.json').exists()
    monkeypatch.setattr(deploy, 'wait_for_asset', Mock())
    assert deploy.main() == 0
    assert path.read_bytes().startswith(before) and path.read_bytes() != before


def test_no_third_party_packages_are_needed_for_the_publication_entrypoint(tmp_path):
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    # -S omits site-packages; a missing hook must fail safely after all startup imports.
    process = subprocess.run([sys.executable, '-S', '-m', 'pipeline.deploy_hook'], cwd=root,
                             env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True)
    assert process.returncode == 1 and 'not_configured' in process.stdout
    assert not process.stderr


def test_delayed_confirmation_is_not_graded_as_an_earlier_publication(tmp_path):
    import pandas as pd
    from perf.live_record import last_run_per_day, match_forecasts
    asset, _ = candidate(tmp_path)
    confirmed.record_confirmed(asset, tmp_path, datetime(2026, 11, 26, tzinfo=timezone.utc))
    frame = pd.read_csv(tmp_path / 'forecast_ledger.csv')
    late = frame[frame.model_hash == '0123456789abcdef']
    assert late.iloc[0].as_of_date == '2026-11-26' and late.iloc[0]['T'] == -2
    events = pd.DataFrame([{'tid': 1, 'family': 'Example Open', 'tournament_year': 2026,
                            'start': pd.Timestamp('2026-11-24'), 'final_count': 10}])
    assert not match_forecasts(last_run_per_day(late), events)
    receipt = next(iter(json.loads((tmp_path / 'forecast_publications.json').read_bytes()).values()))
    assert receipt['producer_run_ts'] == '2026-11-10 12:00:00'
    assert receipt['verified_at'].startswith('2026-11-26')


def test_receipt_write_failure_rolls_back_ledger_and_retry_is_idempotent(tmp_path, monkeypatch):
    asset, _ = candidate(tmp_path)
    path = tmp_path / 'forecast_ledger.csv'
    before = path.read_bytes()
    real_write = Path.write_text

    def fail_receipt(self, *args, **kwargs):
        if self.name == 'forecast_publications.json':
            raise OSError('synthetic receipt failure')
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', fail_receipt)
    with pytest.raises(OSError, match='receipt failure'):
        confirmed.record_confirmed(asset, tmp_path)
    assert path.read_bytes() == before
    assert not (tmp_path / 'forecast_publications.json').exists()
    monkeypatch.setattr(Path, 'write_text', real_write)
    assert confirmed.record_confirmed(asset, tmp_path) == 1
    after = path.read_bytes()
    assert confirmed.record_confirmed(asset, tmp_path) == 0
    assert path.read_bytes() == after


def test_confirmed_recording_succeeds_without_site_packages(tmp_path):
    import subprocess
    import sys

    asset, _ = candidate(tmp_path)
    payload = tmp_path / 'asset.json'
    payload.write_bytes(asset)
    code = ('from pathlib import Path; import sys; '
            'from pipeline.confirmed_publication import record_confirmed; '
            'assert record_confirmed(Path(sys.argv[1]).read_bytes(), Path(sys.argv[2])) == 1')
    root = Path(__file__).resolve().parents[1]
    process = subprocess.run([sys.executable, '-S', '-c', code, str(payload), str(tmp_path)],
                             cwd=root, env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert (tmp_path / 'forecast_publications.json').is_file()
