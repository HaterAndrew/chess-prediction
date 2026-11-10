"""A queued build must become the exact public asset; credentials stay confined."""
import json
import urllib.error
from unittest.mock import Mock

import pytest
import yaml
from pathlib import Path

from pipeline import deploy_hook as deploy

HOOK = 'https://api.cloudflare.com/client/v4/workers/builds/deploy_hooks/synthetic-hook-identifier'
BUILD = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'


def response(body, status=200):
    item = Mock(status=status)
    item.read.return_value = body
    item.__enter__ = Mock(return_value=item)
    item.__exit__ = Mock(return_value=False)
    return item


def accepted(**changes):
    return json.dumps({'success': True, 'result': {'build_uuid': BUILD, 'branch': 'main',
                                                'worker': 'chessentries', **changes}}).encode()


def test_real_request_targets_only_the_configured_hook_and_requires_its_identity():
    opener = Mock()
    opener.open.return_value = response(accepted())
    assert deploy.request_build(HOOK, opener) == BUILD
    req = opener.open.call_args.args[0]
    assert req.full_url == HOOK and req.get_method() == 'POST' and req.data == b''
    assert not req.has_header('Authorization')
    opener.open.return_value = response(json.dumps({'success': True, 'result': {
        'build_uuid': BUILD, 'status': 'queued', 'created_on': '2026-11-10T18:30:00Z',
        'already_exists': False}}).encode())
    assert deploy.request_build(HOOK, opener) == BUILD
    for result in [accepted(worker='other'), accepted(branch='other'), accepted(build_uuid='invalid'),
                   b'null', b'[]', b'bad', b'{"success":false}', b'x' * 8193]:
        opener.open.return_value = response(result)
        with pytest.raises(deploy.DeployError):
            deploy.request_build(HOOK, opener)


@pytest.mark.parametrize('url', ['', 'http://api.cloudflare.com/client/v4/workers/builds/deploy_hooks/abcdefghijklmnop',
    HOOK + '?query=x', HOOK + '#fragment', HOOK + '/extra', HOOK + '\n',
    HOOK.replace('api.cloudflare.com', 'api.cloudflare.com@attacker.test'),
    HOOK.replace('api.cloudflare.com', 'attacker.test'),
    HOOK.replace('api.cloudflare.com', 'synthetic-secret＠api.cloudflare.com')])
def test_foreign_or_malformed_destinations_are_refused_before_transport(url):
    opener = Mock()
    with pytest.raises(deploy.DeployError):
        deploy.request_build(url, opener)
    opener.open.assert_not_called()


def test_redirect_and_transport_errors_do_not_disclose_the_hook(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'docs/data').mkdir(parents=True)
    (tmp_path / 'docs/data/website_data.json').write_bytes(b'expected')
    monkeypatch.setenv('CLOUDFLARE_DEPLOY_HOOK', HOOK)
    opener = Mock()
    opener.open.side_effect = urllib.error.HTTPError(HOOK, 302, HOOK, {}, None)
    monkeypatch.setattr(deploy.urllib.request, 'build_opener', lambda handler: opener)
    assert deploy.NoRedirect().redirect_request(None, None, 302, None, None, 'https://attacker.test') is None
    assert deploy.main() == 1
    assert HOOK not in capsys.readouterr().out


def test_publication_retries_old_bytes_and_network_errors_but_never_reports_them_as_success():
    opener = Mock()
    opener.open.side_effect = [response(b'old'), urllib.error.URLError('offline'), response(b'expected')]
    deploy.wait_for_asset(b'expected', opener, attempts=3, delay=0)
    assert all(call.args[0].full_url == deploy.ASSET_URL for call in opener.open.call_args_list)
    opener.open.side_effect = [response(b'old'), response(b'old')]
    with pytest.raises(deploy.DeployError, match='did_not_match'):
        deploy.wait_for_asset(b'expected', opener, attempts=2, delay=0)


def test_missing_secret_fails_before_any_network_or_false_publication(monkeypatch, capsys):
    monkeypatch.delenv('CLOUDFLARE_DEPLOY_HOOK', raising=False)
    assert deploy.main() == 1
    assert 'not_configured' in capsys.readouterr().out


def test_publication_workflow_and_actual_callers_require_trusted_main():
    path = Path(__file__).resolve().parents[1] / '.github/workflows/publish_worker.yml'
    config = yaml.safe_load(path.read_text())
    trigger = config.get('on', config.get(True))
    assert set(trigger) == {'workflow_dispatch'}
    assert config['permissions'] == {'contents': 'read'}
    job = config['jobs']['publish']
    assert "github.ref == 'refs/heads/main'" in job['if']
    assert job['steps'][0]['with'] == {'ref': 'main', 'persist-credentials': False}
    for filename, primary in [('daily_update.yml', 'scrape-and-update'), ('enrichment_scrapers.yml', 'enrichment')]:
        caller = yaml.safe_load((path.parent / filename).read_text())['jobs'][primary]
        assert caller['concurrency'] == config['concurrency']
        steps = caller['steps']
        publish = next(step for step in steps if step.get('id') == 'publish')
        assert 'always()' in publish['if'] and "github.ref == 'refs/heads/main'" in publish['if']
        assert "github.repository == 'HaterAndrew/chess-prediction'" in publish['if']
        assert "steps.commit.outcome == 'success'" in publish['if']
        assert publish['env'] == {'CLOUDFLARE_DEPLOY_HOOK': '${{ secrets.CLOUDFLARE_DEPLOY_HOOK }}'}
        commit = next(step for step in steps if step.get('name') == 'Commit confirmed publication provenance')
        assert "steps.publish.outcome == 'success'" in commit['if']
        assert 'forecast_publications.json' in commit['run']


def test_malformed_authority_is_sanitized_by_cli(monkeypatch, capsys):
    value = HOOK.replace('api.cloudflare.com', 'synthetic-secret＠api.cloudflare.com')
    monkeypatch.setenv('CLOUDFLARE_DEPLOY_HOOK', value)
    assert deploy.main() == 1
    output = capsys.readouterr()
    assert 'synthetic-secret' not in output.out + output.err


def test_malformed_http_status_is_sanitized_by_cli(monkeypatch, capsys, tmp_path):
    import http.client

    monkeypatch.chdir(tmp_path)
    (tmp_path / 'docs/data').mkdir(parents=True)
    (tmp_path / 'docs/data/website_data.json').write_bytes(b'expected')
    monkeypatch.setenv('CLOUDFLARE_DEPLOY_HOOK', HOOK)
    opener = Mock()
    opener.open.side_effect = http.client.BadStatusLine(HOOK)
    monkeypatch.setattr(deploy.urllib.request, 'build_opener', lambda _: opener)
    assert deploy.main() == 1
    output = capsys.readouterr()
    assert HOOK not in output.out + output.err


def test_native_opener_refuses_redirect_without_a_second_request(monkeypatch, capsys, tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen.append(self.path)
            self.send_response(200)
            self.end_headers()

        def do_POST(self):
            seen.append(self.path)
            self.send_response(302)
            self.send_header('Location', '/unexpected-redirect')
            self.end_headers()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # The destination validator is tested separately. This loopback fixture
        # exercises the actual urllib opener and redirect handler without a key.
        local = f'http://127.0.0.1:{server.server_port}/synthetic-hook'
        monkeypatch.setattr(deploy, 'hook_url', lambda _: local)
        monkeypatch.chdir(tmp_path)
        (tmp_path / 'docs/data').mkdir(parents=True)
        (tmp_path / 'docs/data/website_data.json').write_bytes(b'expected')
        assert deploy.main() == 1
        assert seen == ['/synthetic-hook']
        # A normal opener follows the same 302 as GET, proving the fixture
        # records the second request that the production handler refuses.
        with deploy.urllib.request.build_opener().open(
                deploy.urllib.request.Request(local, data=b'', method='POST'), timeout=2):
            pass
        assert seen == ['/synthetic-hook', '/synthetic-hook', '/unexpected-redirect']
        assert local not in capsys.readouterr().out
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
