"""
Parity gate: worker/src/entrylist_codes.mjs vs scrape_entries.py.

The CCA family->code map and the code-derivation rule exist twice: the
Python original in scrape_entries.py (used by the daily scraper and the
hotel_audit CLI) and the ESM port in worker/src/entrylist_codes.mjs (used
by the Cloudflare worker's /cca-entrylist proxy for the PWA Audit tab).
This test executes the .mjs under node and compares both the full map and
a spread of derivation cases, so an edit to one copy fails loudly until
the other matches. Skipped when node is unavailable.
"""

import json
import os
import shutil
import subprocess


import pytest

from scrape_entries import (
    ENTRY_LIST_CODES,
    ENTRY_LIST_URL_TEMPLATE,
    _derive_entry_list_code,
)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MJS_PATH = os.path.join(PROJECT_DIR, "worker", "src", "entrylist_codes.mjs")

DERIVATION_CASES = [
    "southern open",
    "2026 Southern Open",
    "world open",
    "2026 World Open",
    "chicago open blitz",     # longest-match-first: must beat "chicago open"
    "chicago open",
    "mid-america open",
    "Made Up Open",           # initials fallback
    "the open of and in at",  # skip-words only -> initials of nothing
    "",
]

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)


def _run_mjs():
    script = f"""
    import {{ ENTRY_LIST_CODES, ENTRY_LIST_URL_TEMPLATE, deriveEntryListCode, entryListUrl }}
      from {json.dumps(MJS_PATH)};
    const cases = {json.dumps(DERIVATION_CASES)};
    console.log(JSON.stringify({{
      codes: ENTRY_LIST_CODES,
      template: ENTRY_LIST_URL_TEMPLATE,
      derived: cases.map((c) => deriveEntryListCode(c)),
      sample_url: entryListUrl("SO", 2026),
    }}));
    """
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def test_map_matches_python():
    js = _run_mjs()
    assert js["codes"] == ENTRY_LIST_CODES


def test_url_template_matches_python():
    js = _run_mjs()
    assert js["template"] == ENTRY_LIST_URL_TEMPLATE


def test_derivation_matches_python():
    js = _run_mjs()
    py = [_derive_entry_list_code(c) for c in DERIVATION_CASES]
    assert js["derived"] == py


def test_url_construction():
    js = _run_mjs()
    assert js["sample_url"] == ENTRY_LIST_URL_TEMPLATE.format(code="SO", yy="26")
