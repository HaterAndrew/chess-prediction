"""Next season's events open registration during the current season.

2026-09-17: CCA had nine 2027 events accepting entries (Boston Chess Congress
through the Atlantic City Open) and none reached the site. `_parse_index` kept
only cards carrying the literal "2026", and `sync_metadata` keyed metadata rows
on the family alone under a literal year, so a 2027 edition could neither be
scraped nor stored beside the 2026 edition of the same family.

An edition is (family, year). These tests pin that identity through the scraper.
"""
import csv

import pytest

from scrapers import entries
from scrapers.metadata_sync import sync_metadata
from shared.editions import split_edition_name
from shared.season import is_open_season, CURRENT_SEASON


def _card(name, start, end, state, count, tid="abc=="):
    return (
        f'<div class="card"><a href="tournaments/index.php?view=zNTizdLa&amp;tid={tid}">'
        f'{name}</a><div class="text-muted small">{start} - {end}'
        f' &nbsp; State: {state} </div><span>Entry List [{count}]</span></div>'
    )


# ── edition names ────────────────────────────────────────────────────────

@pytest.mark.parametrize("name, expected", [
    ("2027 Atlantic City Open", ("Atlantic City Open", 2027)),
    ("2026 World Open, top 6 sections", ("World Open, top 6 sections", 2026)),
    ("Atlantic City Open", ("Atlantic City Open", None)),
    ("  2027   Liberty Bell Open ", ("Liberty Bell Open", 2027)),
])
def test_split_edition_name(name, expected):
    assert split_edition_name(name) == expected


def test_split_edition_name_tolerates_non_strings():
    assert split_edition_name(None) == (None, None)


def test_open_season_is_current_or_later():
    assert is_open_season(CURRENT_SEASON)
    assert is_open_season(CURRENT_SEASON + 1)
    assert not is_open_season(CURRENT_SEASON - 1)
    assert not is_open_season(None)
    assert not is_open_season("not a year")


# ── index parse ──────────────────────────────────────────────────────────

def test_parse_index_keeps_next_season_cards():
    html = (
        _card("2026 North American Open", "Dec 26, 2026", "Dec 30, 2026", "Nevada", 136, "a==")
        + _card("2027 Atlantic City Open", "Mar 24, 2027", "Mar 28, 2027", "New Jersey", 1, "b==")
    )
    got = {t["name"]: t for t in entries._parse_index(html, first_season=2026)}
    assert set(got) == {"2026 North American Open", "2027 Atlantic City Open"}
    assert got["2027 Atlantic City Open"]["year"] == 2027
    assert got["2027 Atlantic City Open"]["start_date"] == "2027-03-24"
    assert got["2026 North American Open"]["year"] == 2026


def test_parse_index_keeps_zero_entry_cards():
    # Registration is open the moment CCA lists the card; nobody has to have
    # entered yet for the event to belong on the site.
    html = _card("2027 Golden State Open", "Jan 15, 2027", "Jan 18, 2027", "California", 0)
    got = entries._parse_index(html, first_season=2026)
    assert [t["entry_count"] for t in got] == [0]


def test_parse_index_drops_past_seasons():
    html = _card("2025 North American Open", "Dec 26, 2025", "Dec 30, 2025", "Nevada", 900)
    assert entries._parse_index(html, first_season=2026) == []


def test_parse_index_reads_the_year_from_the_dates_when_the_name_has_none():
    html = _card("Boston Chess Congress", "Jan 08, 2027", "Jan 10, 2027", "Massachusetts", 1)
    got = entries._parse_index(html, first_season=2026)
    assert [t["year"] for t in got] == [2027]


# ── entry-list URL ───────────────────────────────────────────────────────

def test_entry_list_url_uses_the_editions_own_year():
    url_27 = entries._entry_list_url({"name": "2027 Atlantic City Open", "year": 2027})
    url_26 = entries._entry_list_url({"name": "2026 Atlantic City Open", "year": 2026})
    assert "CCA_ACO27/CCA_ACO27_alp_n.html" in url_27
    assert "CCA_ACO26/CCA_ACO26_alp_n.html" in url_26


# ── metadata sync ────────────────────────────────────────────────────────

META_FIELDS = ["family", "year", "start_date", "end_date", "venue_state", "regular_fee"]


def _write_meta(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=META_FIELDS)
        w.writeheader()
        w.writerows(rows)


def _read_meta(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def _aco(year, start, end, **extra):
    row = {"family": "Atlantic City Open", "year": str(year), "start_date": start,
           "end_date": end, "venue_state": "New Jersey", "regular_fee": ""}
    row.update(extra)
    return row


def test_sync_adds_next_season_row_beside_the_current_one(tmp_path):
    meta = tmp_path / "tournament_metadata.csv"
    _write_meta(meta, [_aco(2026, "2026-03-25", "2026-03-29", regular_fee="250")])

    sync_metadata([{"name": "2027 Atlantic City Open", "year": 2027,
                    "start_date": "2027-03-24", "end_date": "2027-03-28",
                    "state": "New Jersey"}], meta_path=str(meta))

    rows = {r["year"]: r for r in _read_meta(meta)}
    assert set(rows) == {"2026", "2027"}
    # The finished edition keeps its own dates and fee.
    assert rows["2026"]["start_date"] == "2026-03-25"
    assert rows["2026"]["regular_fee"] == "250"
    assert rows["2027"]["start_date"] == "2027-03-24"
    assert rows["2027"]["venue_state"] == "New Jersey"


def test_sync_updates_only_the_matching_edition(tmp_path):
    meta = tmp_path / "tournament_metadata.csv"
    _write_meta(meta, [_aco(2026, "2026-03-25", "2026-03-29"),
                       _aco(2027, "2027-03-17", "2027-03-21")])

    sync_metadata([{"name": "2027 Atlantic City Open", "year": 2027,
                    "start_date": "2027-03-24", "end_date": "2027-03-28",
                    "state": "New Jersey"}], meta_path=str(meta))

    rows = {r["year"]: r for r in _read_meta(meta)}
    assert rows["2026"]["start_date"] == "2026-03-25"
    assert rows["2027"]["start_date"] == "2027-03-24"
    assert len(_read_meta(meta)) == 2


def test_sync_is_idempotent(tmp_path):
    meta = tmp_path / "tournament_metadata.csv"
    _write_meta(meta, [_aco(2026, "2026-03-25", "2026-03-29")])
    scraped = [{"name": "2027 Atlantic City Open", "year": 2027,
                "start_date": "2027-03-24", "end_date": "2027-03-28",
                "state": "New Jersey"}]
    sync_metadata(scraped, meta_path=str(meta))
    sync_metadata(scraped, meta_path=str(meta))
    assert len(_read_meta(meta)) == 2


# ── CCA typos ────────────────────────────────────────────────────────────

def test_cca_family_fixes_the_typo_cca_publishes_every_year():
    # CCA has spelled this card "Championshps" since 2024. Unrepaired, the 2027
    # card read as a new family and published the no-history default.
    from tournament_aliases import cca_family
    assert cca_family("2027 Western Class Championshps") == "Western Class Championships"


def test_sync_files_a_typod_card_under_the_repaired_family(tmp_path):
    meta = tmp_path / "tournament_metadata.csv"
    _write_meta(meta, [{"family": "Western Class Championships", "year": "2026",
                        "start_date": "2026-03-05", "end_date": "2026-03-08",
                        "venue_state": "", "regular_fee": ""}])
    sync_metadata([{"name": "2027 Western Class Championshps", "year": 2027,
                    "start_date": "2027-03-12", "end_date": "2027-03-14",
                    "state": "California"}], meta_path=str(meta))
    assert {(r["family"], r["year"]) for r in _read_meta(meta)} == {
        ("Western Class Championships", "2026"), ("Western Class Championships", "2027")}
