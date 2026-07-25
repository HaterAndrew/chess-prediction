"""
Parity gate: docs/audit.js vs hotel_audit.py.

The audit merge logic exists twice: the Python original (hotel_audit.py,
the CLI) and the browser port (docs/audit.js, the PWA Audit tab). This
test feeds identical inputs to both build_people implementations — the
real HTML fixture parsed by the PYTHON parser (the JS DOMParser half is
browser-only and covered by the manual e2e), the shared CSV fixture, and
a helper-function case battery — and compares full outputs, so the two
implementations cannot drift silently. Skipped when node is unavailable.
"""

import json
import os
import shutil
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import pytest

from hotel_audit import (
    build_people,
    dedup_scraped,
    load_export,
    name_key,
    pad_zip,
    parse_entry_list,
    smart_case,
    split_last_first,
)

DRIVER = os.path.join(os.path.dirname(__file__), "js", "audit_parity_driver.js")
FIXTURE_HTML = os.path.join(os.path.dirname(__file__), "fixtures",
                            "cca_entry_list_wo26.html")
FIXTURE_CSV = os.path.join(os.path.dirname(__file__), "fixtures",
                           "admin_export_sample.csv")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not installed"
)

SMART_CASE_CASES = ["JANOWAY", "westmere", "McDonald", "Gianos-Steinberg",
                    "o'brien", "émile", "", "  X Y  "]
PAD_ZIP_CASES = ["2155", "32608", "01748-3233", "", "007", "12345"]
NAME_KEY_CASES = [["Brightwater", "Ana Marie"], ["BRIGHTWATER", "Ana"],
                  ["Ashdown (IM)(Withdrawn)", "Orlando"], ["", ""],
                  ["  Zellwood ", " Jonquil  "]]
SPLIT_CASES = ["Zellwood, Jonquil", "Sunderholm, Zephyr (GM)", "Merrick Janoway",
               "Cher", "JANOWAY, MERRICK", ""]
DEDUP_CASES = [
    {"last": "Zellwood", "first": "Jonquil", "uscf_id": "15524414",
     "state": "NY", "section": "Open", "withdrawn": True},
    {"last": "Zellwood", "first": "Jonquil", "uscf_id": "15524414",
     "state": "NY", "section": "Open", "withdrawn": False},
    {"last": "Zellwood", "first": "Jonquil", "uscf_id": "99999999",
     "state": "NY", "section": "Open", "withdrawn": False},
    {"last": "Lee", "first": "Justin", "uscf_id": None,
     "state": "NY", "section": "Open", "withdrawn": False},
    {"last": "Lee", "first": "Justin M", "uscf_id": None,
     "state": "NY", "section": "Open", "withdrawn": False},
]

STATS_KEYS = ["scraped_players", "scraped_withdrawn", "export_rows",
              "matched_both", "scrape_only", "export_only", "payers_added",
              "payers_already_players", "bulk_payers", "final_people"]


def _canon_people(people):
    return sorted(
        people,
        key=lambda p: (p["last"], p["first"], p["type"], p["source"]),
    )


def _run_driver(payload):
    out = subprocess.run(
        ["node", DRIVER], input=json.dumps(payload),
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def _shared_inputs():
    with open(FIXTURE_HTML, encoding="utf-8") as fh:
        scraped = dedup_scraped(parse_entry_list(fh.read()))
    export_rows = load_export(FIXTURE_CSV)
    with open(FIXTURE_CSV, encoding="utf-8-sig") as fh:
        csv_text = fh.read()
    return scraped, export_rows, csv_text


def test_build_people_parity():
    scraped, export_rows, _ = _shared_inputs()
    py_people, py_stats = build_people(scraped, export_rows)
    js = _run_driver({"scraped": scraped, "export_rows": export_rows})

    assert _canon_people(js["people"]) == _canon_people(py_people)
    py_full = {k: py_stats.get(k, 0) for k in STATS_KEYS}
    assert js["stats"] == py_full


def test_build_people_parity_scrape_only_and_export_only():
    scraped, export_rows, _ = _shared_inputs()
    for payload in ({"scraped": scraped, "export_rows": []},
                    {"scraped": [], "export_rows": export_rows}):
        py_people, py_stats = build_people(payload["scraped"],
                                           payload["export_rows"])
        js = _run_driver(payload)
        assert _canon_people(js["people"]) == _canon_people(py_people)
        assert js["stats"] == {k: py_stats.get(k, 0) for k in STATS_KEYS}


def test_csv_parser_parity():
    _, export_rows, csv_text = _shared_inputs()
    js = _run_driver({"csv_text": csv_text})
    assert js["csv_rows"] == export_rows


def test_helper_parity():
    js = _run_driver({"helper_cases": {
        "smart_case": SMART_CASE_CASES,
        "pad_zip": PAD_ZIP_CASES,
        "name_key": NAME_KEY_CASES,
        "split_last_first": SPLIT_CASES,
        "dedup_scraped": DEDUP_CASES,
    }})
    assert js["helpers"]["smart_case"] == [smart_case(c) for c in SMART_CASE_CASES]
    assert js["helpers"]["pad_zip"] == [pad_zip(c) for c in PAD_ZIP_CASES]
    # Python name_key returns a tuple (last, first_token); the JS port
    # returns the joined string form of the same key.
    assert js["helpers"]["name_key"] == [
        "{} {}".format(*name_key(c[0], c[1])) for c in NAME_KEY_CASES
    ]
    assert js["helpers"]["split_last_first"] == [
        list(split_last_first(c)) for c in SPLIT_CASES
    ]
    assert js["helpers"]["dedup_scraped"] == dedup_scraped(DEDUP_CASES)
