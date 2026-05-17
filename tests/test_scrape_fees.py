"""
Regression tests for scrape_fees.parse_flyer guardrails.

Pinned scenarios:
  * Chicago Open 2026 — genuine early bird (T-63 gap, three tiers, "early
    bird" phrasing). MUST populate early_bird_fee/early_bird_deadline.
  * Cleveland Open 2026 — advance/onsite step only (T-3 gap, two tiers).
    MUST NOT populate early_bird_fee; the $118 advance fee must demote to
    regular_fee with an eb_demoted_reason set.
  * Liberty Bell Open 2026 — three tiers with the cheapest deadline at
    exactly T-14. MUST accept as early bird (boundary case).

These tests use static HTML fixtures in tests/fixtures/flyers/ so they
never hit the live CCA site.
"""

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scrape_fees import parse_flyer, EARLY_BIRD_MIN_GAP_DAYS

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "flyers")


def _load(name):
    with open(os.path.join(FIXTURE_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def test_chicago_open_2026_real_early_bird():
    html = _load("chio26.html")
    out = parse_flyer(html, "https://www.chesstour.com/chio26.htm")
    assert out is not None, "parser returned no record"
    assert out["event_start"] == "2026-05-21"
    # Real early bird: cheapest tier $207 by 3/19 (T-63)
    assert out["early_bird_fee"] == 207
    assert out["early_bird_deadline"] == "2026-03-19"
    assert out["regular_fee"] == 227
    assert out["regular_deadline"] == "2026-05-19"
    assert out["onsite_fee"] == 250
    assert out["has_eb_phrasing"] is True
    assert out["eb_demoted_reason"] == ""


def test_cleveland_open_2026_advance_onsite_no_early_bird():
    """The phantom case from 2026-05-17.

    Cleveland's flyer publishes a two-tier $118/$130 structure with the
    deadline 3 days before the event. The OLD parser labeled $118 as
    early_bird_fee. The new parser MUST demote it.
    """
    html = _load("clev26.html")
    out = parse_flyer(html, "https://www.chesstour.com/clev26.htm")
    assert out is not None
    assert out["event_start"] == "2026-06-05"
    assert out["early_bird_fee"] == ""
    assert out["early_bird_deadline"] == ""
    assert out["regular_fee"] == 118
    assert out["regular_deadline"] == "2026-06-02"
    assert out["onsite_fee"] == 130
    assert "advance/onsite step" in out["eb_demoted_reason"]


def test_liberty_bell_2026_boundary_t14_real_early_bird():
    """Liberty Bell's 1/2 deadline lands exactly at T-14 before the
    1/16 event. The 14-day rule is inclusive — must accept."""
    html = _load("lbo26.html")
    out = parse_flyer(html, "https://www.chesstour.com/lbo26.htm")
    assert out is not None
    assert out["event_start"] == "2026-01-16"
    assert out["early_bird_fee"] == 148
    assert out["early_bird_deadline"] == "2026-01-02"
    # Regular: $158 by 1/15
    assert out["regular_fee"] == 158
    assert out["onsite_fee"] == 180
    assert out["eb_demoted_reason"] == ""


def test_demoted_record_promotes_second_tier_to_onsite_when_missing():
    """When the cheapest tier is demoted and no explicit onsite_fee was
    parsed, the next tier should fill the onsite slot rather than
    leaving the record with only one fee field."""
    html = '''<html><body>
    <h1>Bogus Open</h1>
    <p>May 5, 2026, Anytown.</p>
    <p>Entry fee: $50 by 5/3, $60 by 5/4.</p>
    </body></html>'''
    out = parse_flyer(html, "https://www.chesstour.com/bogus26.htm")
    assert out is not None
    assert out["early_bird_fee"] == ""
    # T-2 gap, gets demoted
    assert "advance/onsite step" in out["eb_demoted_reason"]
    assert out["regular_fee"] == 50
    # second tier filled onsite since none was parsed
    assert out["onsite_fee"] == 60


def test_equal_fees_rejected_as_no_price_hike():
    """If the cheapest two tiers have the same dollar value, that's not a
    hike. parse_flyer must demote even when the gap is large."""
    html = '''<html><body>
    <h1>FlatPrice Open</h1>
    <p>May 21, 2026, Anytown.</p>
    <p>Entry fee: $100 by 3/1, $100 by 5/19.</p>
    </body></html>'''
    out = parse_flyer(html, "https://www.chesstour.com/flat26.htm")
    assert out is not None
    assert out["early_bird_fee"] == ""
    assert "not less than next tier" in out["eb_demoted_reason"]
