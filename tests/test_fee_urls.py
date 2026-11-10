"""Newly linked 2027 flyers must survive scraping and edition resolution."""
import pytest

from fees.parse import parse_flyer
from fees.codes import FAMILY_TO_CODE, UNMAPPED_CODES
from fees.discover import generate_candidate_urls
from registry.keys import fee_edition_key, flyer_code
from registry.exemptions import fee_exemption

BASE = "https://www.chesstour.com/"


def test_high_school_flyer_retains_its_year_and_distinct_family():
    url = BASE + "nyssc27-HighSchool.htm"
    row = parse_flyer("<h1>High School Championships</h1>"
                      "<p>February 27-28, 2027. Entry fee $126 by 2/5.</p>", url)
    assert row["year"] == 2027
    assert row["event_start"] == "2027-02-27"
    assert flyer_code(url) == "nyssc-highschool"
    assert fee_edition_key(url) == ("New York State High School Championship", 2027)
    assert url in generate_candidate_urls()
    assert BASE + "nyssc-highschool27.htm" not in generate_candidate_urls()


def test_senior_flyer_keeps_the_edition_specific_family():
    assert fee_edition_key(BASE + "nyssc26.htm") == (
        "New York State Senior Championship With Young Adult Mi", 2026)
    assert fee_edition_key(BASE + "nyssc27.htm") == (
        "New York State Senior Championship", 2027)


def test_age_group_event_retains_its_existing_registry_family():
    assert fee_edition_key(BASE + "nytoa27.htm") == (
        "Saratoga Tournament Of-The-Ages Open", 2027)
    assert "nytoa" not in UNMAPPED_CODES


@pytest.mark.parametrize("code", ["lbob", "swccb"])
def test_new_separate_event_flyers_are_explicitly_accounted_for(code):
    assert code in UNMAPPED_CODES
    assert code not in FAMILY_TO_CODE.values()
    assert fee_exemption(code)


def test_unknown_flyer_is_still_rejected():
    from registry.keys import UnresolvedKey
    with pytest.raises(UnresolvedKey):
        fee_edition_key(BASE + "unknown27.htm")


def test_suffixed_flyer_is_a_candidate_for_validation():
    from validate_fees import candidate_urls
    assert candidate_urls("New York State High School Championship", 2027)[0] == (
        BASE + "nyssc27-HighSchool.htm")


@pytest.mark.parametrize("filename,expected", [
    ("wog5026.htm", ("wog50", 2026)),
    ("nyssc27-HighSchool.html", ("nyssc-highschool", 2027)),
    ("nyssc27-HighSchool.htm", ("nyssc-highschool", 2027)),
    ("Byes.htm", None), ("bad27.htm.backup", None),
])
def test_flyer_filename_boundaries(filename, expected):
    from fees.urls import flyer_parts
    assert flyer_parts(BASE + filename) == expected


def test_stale_flyer_dates_are_not_rewritten_to_match_the_url_year():
    row = parse_flyer("<h1>High School Championships</h1>"
                      "<p>February 28 - March 1, 2026. Entry fee $126 by 2/5.</p>",
                      BASE + "nyssc27-HighSchool.htm")
    assert row["year"] == 2027
    assert row["event_start"] == "2026-02-28"


@pytest.mark.parametrize("header,expected", [
    ("February 28 - March 1, 2026", "2026-02-28"),
    ("Dec. 30–Jan. 2, 2027", "2026-12-30"),
    ("August 31 - Sept 2, 2026", "2026-08-31"),
    ("Sept. 30 - October 2, 2026", "2026-09-30"),
    ("May 21-25, 22-25, 23-25, or 24-25, 2026", "2026-05-21"),
    ("February 28. Registration ends March 1, 2026", "2026-03-01"),
])
def test_event_start_keeps_the_first_day_of_a_date_range(header, expected):
    from fees.page_text import _guess_event_start
    assert _guess_event_start(header, 2027) == expected


def test_k8_flyer_retains_its_year_and_distinct_family():
    url = BASE + "nyssc26-k8.htm"
    row = parse_flyer("<h1>New York State Scholastic Championships—OPEN TO GRADES K-8 ONLY</h1>"
                      "<p>MARCH 7-8, 2026. Online entry fee, all sections: $120 per player by 2/7, $160 2/8-2/23.</p>", url)
    assert row["year"] == 2026
    assert row["event_start"] == "2026-03-07"
    assert flyer_code(url) == "nyssc-k8"
    assert fee_edition_key(url) == ("New York State Scholastic Championships Grades K-8", 2026)
    assert url in generate_candidate_urls()
    from validate_fees import candidate_urls
    assert candidate_urls("New York State Scholastic Championships Grades K-8", 2027)[0] == BASE + "nyssc27-k8.htm"
    assert fee_edition_key(BASE + "nyssc27.htm") == ("New York State Senior Championship", 2027)
    assert fee_edition_key(BASE + "nyssc27-HighSchool.htm") == ("New York State High School Championship", 2027)


@pytest.mark.parametrize("filename", ["nyssc26-k8.htm", "NYSSC26-K8.HTM", "nyssc26-k8.html?source=listing"])
def test_alphanumeric_flyer_suffix_is_preserved(filename):
    from fees.urls import flyer_parts
    assert flyer_parts(BASE + filename) == ("nyssc-k8", 2026)


@pytest.mark.parametrize("filename", ["nyssc26-8.htm", "nyssc26-k8-extra.htm", "nyssc26-k8.htm.backup"])
def test_unsupported_suffix_shape_is_rejected(filename):
    from fees.urls import flyer_parts
    assert flyer_parts(BASE + filename) is None


def test_alphanumeric_suffix_does_not_authorize_an_unknown_flyer():
    from registry.keys import UnresolvedKey
    with pytest.raises(UnresolvedKey):
        fee_edition_key(BASE + "nyssc26-k9.htm")
