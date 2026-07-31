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



from scrape_fees import parse_flyer

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


def test_event_start_survives_parenthetical_and_cp1252_dashes():
    """The ncc26 header shape (2026-07-31): abbreviated month with a period,
    a split schedule joined by "or", a parenthetical between the day ranges
    and the year, and en dashes that arrive as raw \\x96 bytes when a cp1252
    flyer is decoded as latin-1. All three variants must yield the FIRST
    start day."""
    from fees.parse import _guess_event_start

    variants = [
        # latin-1 decode: 0x96 survives as the C1 control char
        "Example Chess Congress Nov. 27\x9629 or 28\x9629 "
        "(Thanksgiving Weekend), 2026, Anytown Hotel",
        # cp1252/utf-8 decode: proper en dash
        "Example Chess Congress Nov. 27–29 or 28–29 "
        "(Thanksgiving Weekend), 2026, Anytown Hotel",
        # no parenthetical regression check (the pre-fix shape still works)
        "Example Open May 21-25, 22-25, 23-25, or 24-25, 2026",
    ]
    assert _guess_event_start(f"<html><body>{variants[0]}</body></html>", 2026) == "2026-11-27"
    assert _guess_event_start(f"<html><body>{variants[1]}</body></html>", 2026) == "2026-11-27"
    assert _guess_event_start(f"<html><body>{variants[2]}</body></html>", 2026) == "2026-05-21"


# ── v5 Cat F: code-table parity against the real scraped corpus ─────────

def test_every_scraped_2026_code_is_mapped_or_allowlisted():
    """Every flyer code the scraper actually captured must map to some family
    in FAMILY_TO_CODE or be an explicit UNMAPPED_CODES entry —
    TOURNAMENT_CODES and FAMILY_TO_CODE are independently maintained tables,
    and codes falling between them (cono/io/lao/kio/mwcc/nysc/brad) left
    events fee-less while their flyers sat scraped. Reads the real
    output/tournament_fees.csv on purpose: this is data<->code parity, and CI
    runs the tests right after the pipeline regenerates the data."""
    import csv
    import re

    import pytest

    fees_path = os.path.join(PROJECT_DIR, "output", "tournament_fees.csv")
    if not os.path.exists(fees_path):
        pytest.skip("no scraped fee corpus in this checkout")

    from validate_fees import FAMILY_TO_CODE, UNMAPPED_CODES

    with open(fees_path, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("year") == "2026"]
    scraped = set()
    for r in rows:
        m = re.search(r"/([a-z]+)26\.", str(r.get("url", "")))
        if m:
            scraped.add(m.group(1))
    assert scraped, "no 2026 codes parsed from tournament_fees.csv urls"

    mapped = set(FAMILY_TO_CODE.values())
    orphans = scraped - mapped - UNMAPPED_CODES
    assert not orphans, (
        f"scraped flyer code(s) {sorted(orphans)} map to no family and are "
        f"not allowlisted in validate_fees.UNMAPPED_CODES — their events "
        f"cannot receive fees"
    )
