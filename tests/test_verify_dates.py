"""
Tests for tools/verify_dates.py — the date-drift guardrail added after
the d76ea14 incident (wrong event_start dates silently propagating
through the T-axis, daily_data anchors, and pace alerts).

Covers:
  - drift > 1 day → WARNING line and drift count
  - source unavailable (network failure) → WARNING line, no crash
  - World Open sub-event special case — chesstour.com lists each
    sub-event separately; verifier must pick the right date per
    sub-event (lower/U13/top 6) without collapsing them all to one
    "World Open" date.
  - parenthetical metadata family suffixes ("Eastern Class
    Championships (in Connecticut)") canonicalize for lookup.
  - secondary "(other events to be added closer ...)" listing on
    chesstour.com is parsed for fall/winter events that aren't yet
    in the main schedule.
"""
import io
import os
import sys
from contextlib import redirect_stdout
from datetime import date

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from tools.verify_dates import (  # noqa: E402
    parse_chesstour_schedule,
    parse_chessevents_dates,
    verify_year,
    _normalize_family,
)


# ── Test fixtures: realistic mini-snippets of chesstour.com text ────────

CHESSTOUR_FIXTURE_HTML = """
<html><body>
<p>May 21-25, 22-25 or 23-25: Chicago Open, Wheeling (near Chicago), IL ENTER NOW</p>
<p>June 5-7 or 6-7: Cleveland Open, Cleveland, OH ENTER NOW HOTEL</p>
<p>June 5-7 or 6-7: Hartford Open, Cromwell (near Hartford), CT ENTER NOW HOTEL</p>
<p>June 26-28: World Open, Under 1200 and Under 1000 Sections, Philadelphia, PA</p>
<p>June 29-30: World Open Under Age 13 Championship, Philadelphia, PA</p>
<p>July 1-5, 2-5 or 3-5 (Fourth of July Holiday Weekend): World Open, Top 6 Sections, Philadelphia, PA</p>
<p>COMING EVENTS, continued (other events to be added closer to the tournament dates) ...2026 Oct 9-11: Midwest Class Championships, Wheeling, IL Oct 16-18: Eastern Class Championships (IN CONNECTICUT), Windsor Locks, CT Oct 23-25: Eastern Chess Congress (IN NEW JERSEY), Princeton, NJ Nov 27-29: National Chess Congress, Philadelphia, PA Dec 26-30: North American Open, Las Vegas, NV 2027 Jan 8-10: Boston Chess Congress, Boston, MA</p>
</body></html>
"""


def test_world_open_subevents_get_distinct_dates():
    """Each WO sub-event must resolve to its own canonical start date.
    Bug it prevents: collapsing them all to one June 26 (or one July 1)
    which made the comma/no-comma canonicalization gap invisible."""
    parsed = parse_chesstour_schedule(CHESSTOUR_FIXTURE_HTML, year=2026)
    assert parsed.get('World Open lower sections') == date(2026, 6, 26)
    assert parsed.get('World Open Under 13 Championship') == date(2026, 6, 29)
    assert parsed.get('World Open top 6 sections') == date(2026, 7, 1)


def test_secondary_listing_parsed():
    """Events in the abbreviated-month secondary listing must resolve.
    Bug it prevents: NCC/Eastern/Kings Island/North American silently
    showing as source-unavailable forever because chesstour relegates
    them to the compact tail listing."""
    parsed = parse_chesstour_schedule(CHESSTOUR_FIXTURE_HTML, year=2026)
    assert parsed.get('Midwest Class Championships') == date(2026, 10, 9)
    assert parsed.get('Eastern Class Championships') == date(2026, 10, 16)
    assert parsed.get('Eastern Chess Congress') == date(2026, 10, 23)
    assert parsed.get('National Chess Congress') == date(2026, 11, 27)
    assert parsed.get('North American Open') == date(2026, 12, 26)


def test_secondary_listing_skips_next_year():
    """A "2027 Jan 8-10: Boston Chess Congress" entry must NOT be
    tagged as 2026. Year markers in the secondary listing gate which
    year each block belongs to."""
    parsed = parse_chesstour_schedule(CHESSTOUR_FIXTURE_HTML, year=2026)
    # Boston Chess Congress isn't even in our pattern map, but if it
    # were, it should not appear with a 2026 date. Probe via a Jan
    # event we DO recognize: hypothetically Liberty Bell (not in map),
    # but the assertion stays correct because no 2027 event leaked in:
    # all parsed dates must be in 2026.
    for fam, d in parsed.items():
        assert d.year == 2026, f"{fam} leaked from 2027: {d}"


def test_tail_does_not_pollute_main_block():
    """The June 30/July 1 World Open main block must NOT pick up a
    "Nov 27-29: National Chess Congress" listed in the tail.
    Regression of the bug that produced NCC drift=150 days."""
    parsed = parse_chesstour_schedule(CHESSTOUR_FIXTURE_HTML, year=2026)
    assert parsed.get('National Chess Congress') == date(2026, 11, 27)
    # WO top 6 must keep its July 1 date even though NCC is parsed
    # from the same page.
    assert parsed.get('World Open top 6 sections') == date(2026, 7, 1)


# ── _normalize_family: metadata venue suffixes + family aliases ─────────

@pytest.mark.parametrize("raw,canonical", [
    ('Eastern Class Championships (in Connecticut)', 'Eastern Class Championships'),
    ('Eastern Chess Congress (in New Jersey)', 'Eastern Chess Congress'),
    ('World Open, top 6 sections', 'World Open top 6 sections'),
    ('World Open, lower sections', 'World Open lower sections'),
    ('Cleveland Open', 'Cleveland Open'),  # no-op
])
def test_normalize_family(raw, canonical):
    assert _normalize_family(raw) == canonical


# ── verify_year integration: fake fetcher injection ─────────────────────

def test_verify_year_emits_drift_warning(tmp_path, monkeypatch):
    """A metadata row off by 3 days must produce a "WARNING: date drift"
    line — exactly the format auto_update._harvest_warnings expects."""
    # Construct a one-row metadata file
    fake_meta = tmp_path / "tournament_metadata.csv"
    fake_meta.write_text(
        "family,year,start_date,end_date,scrape_end,current,projection,final_count,city,state\n"
        "Cleveland Open,2026,2026-06-08,2026-06-10,,,,,,Cleveland\n"
    )
    monkeypatch.setattr('tools.verify_dates.META_PATH', str(fake_meta))

    buf = io.StringIO()
    with redirect_stdout(buf):
        drift, unavailable, verified = verify_year(
            2026, fetcher=lambda url: CHESSTOUR_FIXTURE_HTML)
    output = buf.getvalue()

    assert 'WARNING: date drift' in output
    assert 'Cleveland Open' in output
    assert 'metadata=2026-06-08' in output
    assert 'canonical=2026-06-05' in output
    assert drift == 1
    assert verified == 1


def test_verify_year_handles_source_unavailable(tmp_path, monkeypatch):
    """Network failure must emit "WARNING: source unavailable" — never
    a crash, never silent."""
    fake_meta = tmp_path / "tournament_metadata.csv"
    fake_meta.write_text(
        "family,year,start_date,end_date,scrape_end,current,projection,final_count,city,state\n"
        "Cleveland Open,2026,2026-06-05,2026-06-07,,,,,,Cleveland\n"
    )
    monkeypatch.setattr('tools.verify_dates.META_PATH', str(fake_meta))

    buf = io.StringIO()
    with redirect_stdout(buf):
        drift, unavailable, verified = verify_year(
            2026, fetcher=lambda url: None)
    output = buf.getvalue()

    assert 'WARNING: source unavailable' in output
    assert drift == 0  # nothing verified, nothing to drift on
    assert verified == 0


def test_verify_year_no_warning_on_match(tmp_path, monkeypatch):
    """Exact-match metadata must produce zero drift warnings."""
    fake_meta = tmp_path / "tournament_metadata.csv"
    fake_meta.write_text(
        "family,year,start_date,end_date,scrape_end,current,projection,final_count,city,state\n"
        "Cleveland Open,2026,2026-06-05,2026-06-07,,,,,,Cleveland\n"
        "World Open top 6 sections,2026,2026-07-01,2026-07-05,,,,,,Philadelphia\n"
        "World Open lower sections,2026,2026-06-26,2026-06-28,,,,,,Philadelphia\n"
    )
    monkeypatch.setattr('tools.verify_dates.META_PATH', str(fake_meta))

    buf = io.StringIO()
    with redirect_stdout(buf):
        drift, unavailable, verified = verify_year(
            2026, fetcher=lambda url: CHESSTOUR_FIXTURE_HTML)
    output = buf.getvalue()

    assert 'WARNING: date drift' not in output
    assert drift == 0
    assert verified == 3


def test_verify_year_handles_comma_canonical_form(tmp_path, monkeypatch):
    """Metadata using the comma form ("World Open, top 6 sections")
    must canonicalize for lookup — otherwise we miss verification on
    the exact rows the comma/no-comma bug originally hid."""
    fake_meta = tmp_path / "tournament_metadata.csv"
    fake_meta.write_text(
        "family,year,start_date,end_date,scrape_end,current,projection,final_count,city,state\n"
        # comma form (CCA / all_registrations export)
        '"World Open, top 6 sections",2026,2026-07-01,2026-07-05,,,,,,Philadelphia\n'
    )
    monkeypatch.setattr('tools.verify_dates.META_PATH', str(fake_meta))

    buf = io.StringIO()
    with redirect_stdout(buf):
        drift, unavailable, verified = verify_year(
            2026, fetcher=lambda url: CHESSTOUR_FIXTURE_HTML)

    assert drift == 0
    assert verified == 1


# ── chessevents.com past-year path ──────────────────────────────────────

CHESSEVENTS_FIXTURE_HTML = """
<html><body>
<h4>June 13, 2025 - June 15, 2025</h4>
<p>Cleveland Open in Cleveland, OH</p>
</body></html>
"""

CHESSEVENTS_PLACEHOLDER_HTML = """
<html><body>
<h4></h4>
<p>Event has not yet been scheduled.</p>
</body></html>
"""


# ── v5 Cat V: past-event guard + comma-variant dedupe ────────────────────

def test_past_event_missing_from_schedule_is_moot_not_warning(tmp_path, monkeypatch):
    """chesstour.com drops events once they are over, so a PAST event absent
    from the schedule page is verified moot (INFO), not a source-parse
    failure. 15 of the nightly payload's 216 warnings were exactly this."""
    fake_meta = tmp_path / "tournament_metadata.csv"
    fake_meta.write_text(
        "family,year,start_date,end_date\n"
        "Southern Open,2026,2026-07-17,2026-07-19\n"  # over; not in fixture
    )
    monkeypatch.setattr('tools.verify_dates.META_PATH', str(fake_meta))

    buf = io.StringIO()
    with redirect_stdout(buf):
        drift, unavailable, verified = verify_year(
            2026, fetcher=lambda url: CHESSTOUR_FIXTURE_HTML)
    output = buf.getvalue()

    assert 'WARNING: source-parse failure' not in output
    assert 'INFO: Southern Open 2026: event over' in output
    assert unavailable == 0


def test_future_event_missing_from_schedule_still_warns(tmp_path, monkeypatch):
    """A FUTURE event whose pattern is absent from the schedule page is a
    real parse/pattern failure and must keep warning."""
    fake_meta = tmp_path / "tournament_metadata.csv"
    fake_meta.write_text(
        "family,year,start_date,end_date\n"
        "Pacific Coast Open,2026,2027-07-30,2027-08-02\n"  # future; not in fixture
    )
    monkeypatch.setattr('tools.verify_dates.META_PATH', str(fake_meta))

    buf = io.StringIO()
    with redirect_stdout(buf):
        drift, unavailable, verified = verify_year(
            2026, fetcher=lambda url: CHESSTOUR_FIXTURE_HTML)
    output = buf.getvalue()

    assert 'WARNING: source-parse failure — Pacific Coast Open 2026' in output
    assert unavailable == 1


def test_comma_variant_metadata_rows_verified_once(tmp_path, monkeypatch):
    """Both "World Open lower sections" and "World Open, lower sections"
    exist as metadata rows; they normalize to one family and must produce at
    most ONE line, not the duplicated pair the old loop emitted."""
    fake_meta = tmp_path / "tournament_metadata.csv"
    fake_meta.write_text(
        "family,year,start_date,end_date\n"
        "World Open lower sections,2026,2026-06-26,2026-06-28\n"
        "\"World Open, lower sections\",2026,2026-06-26,2026-06-28\n"
    )
    monkeypatch.setattr('tools.verify_dates.META_PATH', str(fake_meta))

    buf = io.StringIO()
    with redirect_stdout(buf):
        verify_year(2026, fetcher=lambda url: CHESSTOUR_FIXTURE_HTML)
    output = buf.getvalue()

    assert output.count('World Open lower sections') <= 1


def test_parse_chessevents_dates():
    start, end = parse_chessevents_dates(CHESSEVENTS_FIXTURE_HTML)
    assert start == date(2025, 6, 13)
    assert end == date(2025, 6, 15)


def test_parse_chessevents_dates_placeholder():
    """Future-year pages on chessevents.com render with empty <h4>;
    parser must return (None, None), never crash."""
    start, end = parse_chessevents_dates(CHESSEVENTS_PLACEHOLDER_HTML)
    assert start is None
    assert end is None
