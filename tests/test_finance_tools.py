"""Secret-handling checks use synthetic values and never sign into Chess Action."""
import json
import os
import runpy
import http.cookiejar
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from tools.finance_credentials import read_private_json, write_private_json
from tools.finance_login import FormInputs
from tools import finance_probe


def _run_login_fixture(tmp_path, monkeypatch, replies):
    from tools import finance_login
    credentials = tmp_path/'login.json'
    credentials.write_text(json.dumps({'CHESS_ACTION_USERNAME':'synthetic-user',
                                       'CHESS_ACTION_PASSWORD':'synthetic-password'}))
    credentials.chmod(0o600)
    tmp_path.chmod(0o700)
    calls, prompts = [], []
    responses = iter(replies)
    class Reply:
        def __init__(self, url, body): self.url, self.body = url, body
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return self.body.encode()[:limit]
    class Source:
        def __init__(self, jar): self.jar = jar
        def open(self, request, **kwargs):
            calls.append({'path':urlsplit(request.full_url).path,
                          'fields':parse_qs((request.data or b'').decode()),
                          'referer':request.get_header('Referer')})
            url, body = next(responses)
            if "id='tournments'" in body:
                self.jar.set_cookie(http.cookiejar.Cookie(0, 'session', 'synthetic-cookie', None, False,
                    '.chessaction.com', True, True, '/', True, True, None, True, None, None, {}))
            return Reply(url, body)
    def opener(*handlers):
        return Source(next(h.cookiejar for h in handlers if hasattr(h, 'cookiejar')))
    def code(*args):
        prompts.append(True)
        return 'synthetic-code'
    monkeypatch.setattr('urllib.request.build_opener', opener)
    monkeypatch.setattr('getpass.getpass', code)
    monkeypatch.syspath_prepend(str(Path(finance_login.__file__).parent))
    monkeypatch.setattr('sys.argv', ['finance_login.py', str(credentials), str(tmp_path/'session.json')])
    try:
        runpy.run_path(finance_login.__file__, run_name='__main__')
        status = 0
    except SystemExit as error:
        status = error.code
    return status, calls, prompts


ADMIN_FORM = "<form action='login.php' method='post'><input name='username' type='text'><input name='password' type='password'><input name='adminlogin' type='hidden' value='1'><input name='submit' type='submit' value='Login'></form>"
ORDERS = "<h1>Continental Chess Association</h1><select id='tournments'></select>"


def test_login_uses_admin_form_and_adminlogin_field(tmp_path, monkeypatch):
    status, calls, prompts = _run_login_fixture(tmp_path, monkeypatch, [
        ('https://chessaction.com/admin/login.php', ADMIN_FORM),
        ('https://chessaction.com/admin/index.php', 'Dashboard'),
        ('https://chessaction.com/admin/search.php', ORDERS),
    ])
    assert calls[0]['path'] == '/admin/login.php'
    assert status == 0
    assert [c['path'] for c in calls] == ['/admin/login.php', '/admin/login.php', '/admin/search.php']
    assert calls[1]['fields']['adminlogin'] == ['1']
    assert 'regforpay' not in calls[1]['fields']
    assert calls[1]['referer'] == 'https://chessaction.com/admin/login.php'
    assert not prompts
    assert read_private_json(tmp_path/'session.json') == {'CHESS_ACTION_COOKIE':'session=synthetic-cookie'}


@pytest.mark.parametrize(('challenge_url', 'action', 'verify_path'), [
    ('https://chessaction.com/admin/login.php', '../login.php', '/login.php'),
    ('https://chessaction.com/admin/vsecurelogin.php', 'vsecurelogin.php', '/admin/vsecurelogin.php'),
])
def test_admin_verification_follows_its_same_origin_form_action(tmp_path, monkeypatch,
                                                             challenge_url, action, verify_path):
    challenge = f"Enter Login Authentication Code<form action='{action}'><input name='tf_code' type='password'><input name='submit' value='Verify'></form>"
    status, calls, prompts = _run_login_fixture(tmp_path, monkeypatch, [
        ('https://chessaction.com/admin/login.php', ADMIN_FORM),
        (challenge_url, challenge),
        ('https://chessaction.com/index.php', 'Verified'),
        ('https://chessaction.com/admin/search.php', ORDERS),
    ])
    assert status == 0
    assert [c['path'] for c in calls] == ['/admin/login.php', '/admin/login.php', verify_path, '/admin/search.php']
    assert calls[2]['fields']['tf_code'] == ['synthetic-code']
    assert calls[2]['referer'] == challenge_url
    assert len(prompts) == 1


@pytest.mark.parametrize('action', [
    'https://attacker.invalid/collect', '/admin/search.php', '//attacker.invalid/login.php',
    'http://chessaction.com/login.php', 'https://user:synthetic@chessaction.com/login.php',
    'https://chessaction.com:444/login.php', '/login.php?next=synthetic', '/login.php#verify',
    'https://chessaction.com.attacker.invalid/login.php',
])
def test_verification_refuses_unknown_destination_before_code_prompt(tmp_path, monkeypatch, capsys, action):
    challenge = f"Enter Login Authentication Code<form action='{action}'><input name='tf_code' type='password'></form>"
    status, calls, prompts = _run_login_fixture(tmp_path, monkeypatch, [
        ('https://chessaction.com/admin/login.php', ADMIN_FORM),
        ('https://chessaction.com/admin/login.php', challenge),
    ])
    assert status == 1
    assert len(calls) == 2
    assert not prompts
    assert not (tmp_path/'session.json').exists()
    assert 'authentication form destination changed' in capsys.readouterr().out


def test_admin_form_refuses_foreign_action_before_password_submission(tmp_path, monkeypatch):
    status, calls, prompts = _run_login_fixture(tmp_path, monkeypatch, [
        ('https://chessaction.com/admin/login.php', ADMIN_FORM.replace("action='login.php'", "action='https://attacker.invalid/login.php'")),
    ])
    assert status == 1
    assert len(calls) == 1
    assert calls[0]['fields'] == {}
    assert not prompts
    assert not (tmp_path/'session.json').exists()


@pytest.mark.parametrize(('verified_page', 'orders_url', 'expected'), [
    ('Enter Login Authentication Code', 'https://chessaction.com/admin/login.php',
     'Verification returned to the code page; no session was saved'),
    ('Verification finished', 'https://chessaction.com/admin/login.php',
     'Sign-in did not reach Orders; no session was saved'),
])
def test_login_reports_fixed_failure_reason_after_code_entry(tmp_path, monkeypatch, capsys,
                                                           verified_page, orders_url, expected):
    """Exercise the real CLI catch, without sending login requests or real codes."""
    from tools import finance_login
    credentials = tmp_path/'login.json'
    credentials.write_text(json.dumps({'CHESS_ACTION_USERNAME':'synthetic-user',
                                       'CHESS_ACTION_PASSWORD':'synthetic-password'}))
    credentials.chmod(0o600)
    replies = iter([
        ('https://chessaction.com/admin/login.php', ADMIN_FORM),
        ('https://chessaction.com/login.php', "Enter Login Authentication Code<form><input name='tf_code' type='password'><input name='submit' value='Verify'></form>"),
        ('https://chessaction.com/login.php', verified_page),
        (orders_url, 'Sign in'),
    ])
    class Reply:
        def __init__(self, url, body): self.url, self.body = url, body
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return self.body.encode()[:limit]
    class Source:
        def open(self, *args, **kwargs): return Reply(*next(replies))
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Source())
    monkeypatch.setattr('getpass.getpass', lambda *args: 'synthetic-code')
    monkeypatch.syspath_prepend(str(Path(finance_login.__file__).parent))
    monkeypatch.setattr('sys.argv', ['finance_login.py', str(credentials), str(tmp_path/'session.json')])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(finance_login.__file__, run_name='__main__')
    assert stopped.value.code == 1
    output = capsys.readouterr().out
    assert expected in output
    assert 'synthetic-password' not in output
    assert 'synthetic-code' not in output
    assert not (tmp_path/'session.json').exists()


def test_login_does_not_print_arbitrary_runtime_exception_text(tmp_path, monkeypatch, capsys):
    from tools import finance_login
    credentials = tmp_path/'login.json'
    credentials.write_text('{}')
    credentials.chmod(0o600)
    class Source:
        def open(self, *args, **kwargs): raise RuntimeError('synthetic-private-response')
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Source())
    monkeypatch.syspath_prepend(str(Path(finance_login.__file__).parent))
    monkeypatch.setattr('sys.argv', ['finance_login.py', str(credentials), str(tmp_path/'session.json')])
    with pytest.raises(SystemExit):
        runpy.run_path(finance_login.__file__, run_name='__main__')
    output = capsys.readouterr().out
    assert 'Session setup failed' in output
    assert 'synthetic-private-response' not in output


def test_secret_files_are_private_exclusive_and_refuse_symlinks(tmp_path):
    tmp_path.chmod(0o700)
    target = tmp_path / 'session.json'
    write_private_json(target, {'CHESS_ACTION_COOKIE':'synthetic-cookie'})
    assert target.stat().st_mode & 0o777 == 0o600
    assert read_private_json(target) == {'CHESS_ACTION_COOKIE':'synthetic-cookie'}
    with pytest.raises(FileExistsError):
        write_private_json(target, {'replacement':'not written'})
    link = tmp_path / 'link.json'
    link.symlink_to(target)
    with pytest.raises(OSError):
        read_private_json(link)
    assert 'replacement' not in target.read_text()


def test_secret_files_refuse_a_shared_parent_and_group_readable_input(tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError):
        write_private_json(tmp_path/'no.json', {'synthetic':'value'})
    source = tmp_path/'unsafe.json'
    source.write_text('{}')
    source.chmod(0o640)
    with pytest.raises(ValueError):
        read_private_json(source)


def test_code_submission_cannot_select_a_later_resend_form():
    form = FormInputs()
    form.feed("<form><input name='tf_code' type='password'><input name='submit' type='submit' value='Verify'></form>"
              "<form><input name='resend' type='hidden' value='1'><input name='submit' type='submit' value='Resend'></form>")
    assert form.for_control('tf_code') == {'submit':'Verify'}
    assert 'resend' not in form.for_control('tf_code')


def test_probe_with_only_password_credentials_sends_no_requests(tmp_path, monkeypatch):
    path = tmp_path/'credentials.json'
    path.write_text(json.dumps({'CHESS_ACTION_USERNAME':'synthetic-user','CHESS_ACTION_PASSWORD':'synthetic-password'}))
    path.chmod(0o600)
    class NoNetwork:
        def open(self, *args, **kwargs):
            raise AssertionError('A probe without an approved session must not send a request')
    monkeypatch.setattr(finance_probe, 'build_opener', lambda *args: NoNetwork())
    monkeypatch.setattr('sys.argv', ['finance_probe', os.fspath(path)])
    with pytest.raises(ValueError, match='source_session_required'):
        finance_probe.main()
