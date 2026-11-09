#!/usr/bin/env python3
"""Approve a collector session once; authentication codes stay in this terminal."""
import argparse
import getpass
from html.parser import HTMLParser
import http.cookiejar
from pathlib import Path
import re
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, HTTPCookieProcessor, build_opener

if __package__:
    from .finance_probe import SameOrigin
    from .finance_credentials import read_private_json, write_private_json
else:
    from finance_probe import SameOrigin
    from finance_credentials import read_private_json, write_private_json

ORIGIN = 'https://chessaction.com'
SAFE_SETUP_FAILURES = frozenset({
    'The source authentication form changed',
    'The source login form changed',
    'The source admin login form changed',
    'The source authentication form destination changed',
    'Source response too large',
    'A code is required',
    'The verification form includes an unexpected resend action',
    'Verification returned to the code page; no session was saved',
    'Sign-in did not reach Orders; no session was saved',
    'No authenticated cookie was issued',
})


class FormInputs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form':
            self.current = {'names':set(), 'fields':{}, 'action':a.get('action', '')}
            self.forms.append(self.current)
        if tag == 'input' and a.get('name') and self.current is not None:
            self.current['names'].add(a['name'])
            if a.get('type') not in {'button', 'password', 'text'}:
                self.current['fields'][a['name']] = a.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.current = None

    def _form(self, name):
        matches = [form for form in self.forms if name in form['names']]
        if len(matches) != 1:
            raise RuntimeError('The source authentication form changed')
        return matches[0]

    def for_control(self, name):
        return self._form(name)['fields']

    def action_for_control(self, name, page_url):
        action = urlsplit(urljoin(page_url, self._form(name)['action']))
        if (action.scheme != 'https' or action.netloc != 'chessaction.com'
                or action.path not in {'/admin/login.php', '/admin/vsecurelogin.php', '/login.php'}
                or action.query or action.fragment):
            raise RuntimeError('The source authentication form destination changed')
        return action.path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('credentials', type=Path)
    parser.add_argument('destination', type=Path, help='New private JSON file outside the repository')
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    if args.destination.resolve().is_relative_to(repository) or args.destination.exists():
        parser.error('Choose a new destination outside the repository')
    secrets = read_private_json(args.credentials)
    jar = http.cookiejar.CookieJar()
    opener = build_opener(SameOrigin(), HTTPCookieProcessor(jar))

    def read(path, fields=None, referer=None):
        request = Request(ORIGIN + path, data=urlencode(fields).encode() if fields is not None else None,
                          headers={'User-Agent':'Mozilla/5.0 ChessEntries/1.0', 'Origin':ORIGIN,
                                   'Referer':referer or ORIGIN+path})
        with opener.open(request, timeout=25) as response:
            body = response.read(8_000_001)
            if len(body) > 8_000_000:
                raise RuntimeError('Source response too large')
            return response.url, body.decode(errors='replace')

    login_url, page = read('/admin/login.php')
    form = FormInputs()
    form.feed(page)
    fields = form.for_control('username')
    if 'adminlogin' not in fields:
        raise RuntimeError('The source admin login form changed')
    login_path = form.action_for_control('username', login_url)
    verification_url, page = read(login_path, {**fields, 'username':secrets['CHESS_ACTION_USERNAME'],
                                              'password':secrets['CHESS_ACTION_PASSWORD']}, referer=login_url)
    verification_pending = False
    if 'Enter Login Authentication Code' in page:
        form = FormInputs()
        form.feed(page)
        # The separate resend form is not submitted: only verify the entered code.
        fields = form.for_control('tf_code')
        verification_path = form.action_for_control('tf_code', verification_url)
        if 'resend' in fields:
            raise RuntimeError('The verification form includes an unexpected resend action')
        print('Chess Action sent an authentication code. Use the newest email from this sign-in.')
        code = getpass.getpass('Authentication code (hidden): ').strip()
        if not code or len(code) > 128:
            raise RuntimeError('A code is required')
        _, page = read(verification_path, {**fields, 'tf_code':code}, referer=verification_url)
        verification_pending = 'Enter Login Authentication Code' in page
    url, page = read('/admin/search.php')
    if 'login.php' in url or not re.search(r'id\s*=\s*["\']tournments["\']', page):
        if verification_pending:
            raise RuntimeError('Verification returned to the code page; no session was saved')
        raise RuntimeError('Sign-in did not reach Orders; no session was saved')
    cookie = '; '.join(f'{c.name}={c.value}' for c in jar if c.domain.lstrip('.') in {'chessaction.com','www.chessaction.com'})
    if not cookie:
        raise RuntimeError('No authenticated cookie was issued')
    write_private_json(args.destination, {'CHESS_ACTION_COOKIE':cookie})
    print(f'Orders access verified. Saved private session to {args.destination}.')
    print('No credentials or authentication codes were printed.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Only exact, locally defined messages may be printed. Network and
        # arbitrary exception text can contain account data.
        if type(error) is RuntimeError and str(error) in SAFE_SETUP_FAILURES:
            print(f'Session setup failed: {error}.')
        else:
            print(f'Session setup failed ({type(error).__name__}); no secret values were printed.')
        raise SystemExit(1) from None
