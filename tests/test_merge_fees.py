"""Regression tests for the merge_fees date cross-check (H3).

The guard exists so a wrong flyer-code mapping can't paste fees onto the wrong
event. Before H3 the check sat inside a try/except that swallowed any parse
failure with `pass`, meaning an unverifiable date merged the fees anyway — the
exact case the guard is meant to block. These tests lock skip-on-unverifiable.
"""
import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import merge_fees  # noqa: E402

META_COLS = ["family", "year", "regular_fee", "onsite_fee", "early_bird_fee",
             "early_bird_deadline", "start_date"]


def _setup(tmp_path, monkeypatch, flyer_event_start):
    meta = pd.DataFrame([{
        "family": "TestFam", "year": 2026, "regular_fee": "", "onsite_fee": "",
        "early_bird_fee": "", "early_bird_deadline": "", "start_date": "2026-08-01",
    }], columns=META_COLS)
    fees = pd.DataFrame([{
        "year": 2026, "url": "https://chesstour.com/tf26.html",
        "event_start": flyer_event_start, "regular_fee": 100, "onsite_fee": 120,
        "early_bird_fee": 80, "eb_demoted_reason": "", "early_bird_deadline": "2026-07-01",
    }])
    meta_csv = tmp_path / "tournament_metadata.csv"
    fees_csv = tmp_path / "tournament_fees.csv"
    meta.to_csv(meta_csv, index=False)
    fees.to_csv(fees_csv, index=False)
    monkeypatch.setattr(merge_fees, "META_CSV", str(meta_csv))
    monkeypatch.setattr(merge_fees, "FEES_CSV", str(fees_csv))
    monkeypatch.setattr(merge_fees, "FAMILY_TO_CODE", {"TestFam": "tf"})
    return meta_csv


@pytest.mark.parametrize("event_start,expected_filled", [
    ("2026-08-02", 1),     # within ±3 days -> merge
    ("2026-10-01", 0),     # >3 days off    -> skip (mismatch)
    ("not-a-date", 0),     # unparseable    -> skip (H3: was merged before)
    ("", 0),               # missing        -> skip (H3)
])
def test_date_guard(tmp_path, monkeypatch, event_start, expected_filled):
    _setup(tmp_path, monkeypatch, event_start)
    assert merge_fees.merge_fees(dry_run=True) == expected_filled
