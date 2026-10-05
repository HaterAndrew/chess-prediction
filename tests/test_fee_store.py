"""tournament_fees.csv is updated by flyer URL instead of rewritten weekly,
every flyer on file is probed again, and flyer codes may end in digits."""
from fees.discover import CHESSTOUR, flyer_url, generate_candidate_urls
from fees.parse import _guess_title
from fees.store import COLUMNS, read_fees, upsert, write_fees
from registry.keys import fee_edition_key, flyer_code
from shared.season import CURRENT_SEASON


def _row(url, fee, seen=""):
    return dict.fromkeys(COLUMNS, "") | {"url": url, "regular_fee": fee, "last_seen": seen}


def test_upsert_keeps_flyers_this_run_did_not_parse():
    existing = [_row(CHESSTOUR + "so26.htm", "128", "2026-07-13"),
                _row(CHESSTOUR + "eo26.htm", "110", "2026-09-28")]
    parsed = [dict(_row(CHESSTOUR + "eo26.htm", "115"))]
    rows = upsert(existing, parsed, "2026-10-05")
    by_url = {r["url"]: r for r in rows}
    assert by_url[CHESSTOUR + "so26.htm"]["last_seen"] == "2026-07-13"
    assert by_url[CHESSTOUR + "eo26.htm"]["regular_fee"] == "115"
    assert by_url[CHESSTOUR + "eo26.htm"]["last_seen"] == "2026-10-05"
    assert [r["url"] for r in rows] == sorted(by_url)


def test_write_then_read_round_trips(tmp_path):
    path = tmp_path / "tournament_fees.csv"
    rows = [_row(CHESSTOUR + "so26.htm", "128", "2026-07-13")]
    write_fees(path, rows)
    assert read_fees(path) == rows
    assert read_fees(tmp_path / "missing.csv") == []


def test_candidates_cover_known_flyers_and_mapped_codes_next_season():
    known = ["http://www.chesstour.com/woam26.htm"]
    urls = generate_candidate_urls(known)
    assert CHESSTOUR + "woam26.htm" in urls
    assert "http://www.chesstour.com/woam26.htm" not in urls
    next_yy = f"{(CURRENT_SEASON + 1) % 100:02d}"
    assert f"{CHESSTOUR}bcc{next_yy}.htm" in urls
    assert f"{CHESSTOUR}mao{next_yy}.htm" in urls


def test_flyer_url_has_one_spelling():
    assert flyer_url("http://chesstour.com/eo26.htm") == CHESSTOUR + "eo26.htm"


def test_flyer_code_may_end_in_digits():
    assert flyer_code(CHESSTOUR + "wog5026.htm") == "wog50"
    assert flyer_code(CHESSTOUR + "eo26.htm") == "eo"
    assert fee_edition_key(CHESSTOUR + "woam26.htm") == ("World Open Amateur", 2026)


def test_title_drops_a_year_that_is_not_the_flyers():
    html = "<html><head><title>2023 Eastern Open chess tournament</title></head></html>"
    assert _guess_title(html, CHESSTOUR + "eo25.htm") == "Eastern Open chess tournament"
    assert _guess_title(html, CHESSTOUR + "eo23.htm") == "2023 Eastern Open chess tournament"


def test_on_site_fee_below_the_advance_fee_is_dropped():
    from fees.parse import _plausible_onsite
    assert _plausible_onsite(40, 227, CHESSTOUR + "chio22.htm") is None
    assert _plausible_onsite(250, 227, CHESSTOUR + "chio22.htm") == 250
    assert _plausible_onsite(250, "", CHESSTOUR + "x26.htm") == 250
