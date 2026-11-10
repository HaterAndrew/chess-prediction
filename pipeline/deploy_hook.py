"""Request the existing main-branch Worker build and verify its published data."""
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import UUID

ASSET_URL = 'https://chessentries.com/data/website_data.json'
HOOK_PATH = '/client/v4/workers/builds/deploy_hooks/'


class DeployError(RuntimeError):
    """A fixed diagnostic that never includes the credential-bearing URL."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def hook_url(value):
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        raise DeployError('deploy_hook_not_configured_or_invalid') from None
    if (parsed.scheme != 'https' or parsed.netloc != 'api.cloudflare.com'
            or parsed.query or parsed.fragment or not parsed.path.startswith(HOOK_PATH)
            or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', parsed.path[len(HOOK_PATH):])
            or any(ord(c) <= 32 for c in value)):
        raise DeployError('deploy_hook_not_configured_or_invalid')
    return value


def request_build(url, opener):
    request = urllib.request.Request(hook_url(url), data=b'', method='POST',
                                     headers={'User-Agent': 'Chessentries publisher'})
    try:
        with opener.open(request, timeout=10) as response:
            body = response.read(8193)
            if response.status not in (200, 201, 202) or len(body) > 8192:
                raise DeployError('build_request_invalid_response')
            result = json.loads(body)
        build = result.get('result', {})
        # The live endpoint returns build_uuid/status/created_on/already_exists;
        # documented variants also echo the hook's worker and branch. The hook
        # is installed for chessentries/main; reject contrary identity if echoed.
        if (result.get('success') is not True or not isinstance(build, dict)
                or 'worker' in build and build['worker'] != 'chessentries'
                or 'branch' in build and build['branch'] != 'main'):
            raise DeployError('build_request_wrong_target_or_refused')
        return str(UUID(build['build_uuid']))
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        raise DeployError('build_request_failed') from None
    except (ValueError, TypeError, KeyError, AttributeError):
        raise DeployError('build_request_invalid_response') from None


def wait_for_asset(expected, opener, attempts=48, delay=5):
    """A build acknowledgement is insufficient: require the published bytes."""
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(ASSET_URL, headers={
                'User-Agent': 'Chessentries publisher', 'Cache-Control': 'no-cache'})
            with opener.open(request, timeout=10) as response:
                actual = response.read(8_000_001)
                if response.status == 200 and actual == expected:
                    return
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            pass  # A bounded retry; exhaustion is a failing workflow.
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise DeployError('published_assets_did_not_match_main')


def main():
    try:
        url = hook_url(os.environ.get('CLOUDFLARE_DEPLOY_HOOK', ''))
        expected = Path('docs/data/website_data.json').read_bytes()
        if not expected or len(expected) > 8_000_000:
            raise DeployError('published_asset_input_invalid')
        opener = urllib.request.build_opener(NoRedirect())
        build = request_build(url, opener)
        print(f'Worker build accepted: {build}')
        wait_for_asset(expected, opener)
        from pipeline.confirmed_publication import record_confirmed
        count = record_confirmed(expected)
        print(f'Published Worker data matches main; {count} confirmed ledger rows.')
        return 0
    except DeployError as error:
        print(f'Worker publication failed: {error}')
        return 1
    except (OSError, ValueError, TypeError, KeyError):
        print('Worker publication failed: publication_files_unavailable')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
