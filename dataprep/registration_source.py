"""Bounded protected-feed transport; credentials never enter URLs or diagnostics."""

import json
from urllib.parse import urlsplit

import requests

from dataprep.registration_contract import FeedError


def fetch_feed(proxy_url, key):
    url = urlsplit(proxy_url)
    if (
        url.scheme != "https"
        or url.netloc != "chessentries.com"
        or url.path != "/cca-tourlist"
        or url.query
        or url.fragment
    ):
        raise FeedError("Registration feed destination refused")
    if not key:
        raise FeedError("Registration feed credential missing")
    try:
        with requests.get(
            "https://chessentries.com/registration-feed",
            headers={"X-Proxy-Key": key, "User-Agent": "Mozilla/5.0 ChessEntries/1.0"},
            timeout=(10, 60),
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise FeedError(f"Registration feed HTTP {response.status_code}")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 8_000_000:
                    raise FeedError("Registration feed response too large")
                chunks.append(chunk)
            return json.loads(b"".join(chunks))
    except (requests.RequestException, json.JSONDecodeError, UnicodeDecodeError):
        raise FeedError("Registration feed unavailable or invalid JSON") from None
