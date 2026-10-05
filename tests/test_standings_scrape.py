"""The weekly standings scrape reads chessevents.com as served on 2026-10-04
and counts with the cca-site import's rule. Until then it fetched only
archive.chessevents.com, which redirects, and added nothing after
2026-04-20."""
import csv
from datetime import date

import pytest

import scrapers.standings as scrape
from scrapers.chessevents_standings import (StandingsUnreadable, parse_events, parse_sections,
                                            parse_standings)
from standings.count_rule import Section
from standings.due import editions_due
from standings.importer import FolderEdition

ONE_ROW = """<table class="results-table"><thead><tr><th>#</th><th>Name</th><th>ID</th>
<th>Rating</th></tr></thead><tbody>
<tr><td>1</td><td>A</td><td>15346712</td><td>2539</td></tr>
<tr><td>2</td><td>B</td><td></td><td>unr.</td></tr></tbody></table>"""

TWO_ROW = """<table class="results-table"><thead><tr><th>#</th><th>Name/Rating/ID</th>
<th>St/Tm</th><th>Rd 1</th></tr></thead><tbody>
<tr><td data-sort="0">1</td><td>A</td><td>PA</td><td>B 20</td></tr>
<tr><td data-sort="1"></td><td>2043   15680068   A - B</td><td>AB</td><td>1.0</td></tr>
<tr><td data-sort="2">2</td><td>C</td><td>NY</td><td>W 22</td></tr>
<tr><td data-sort="3"></td><td>unr.</td><td></td><td>0.0</td></tr></tbody></table>"""

PAIRINGS = """<table class="results-table"><thead><tr><th>Bd</th><th>Res</th><th>White</th>
</tr></thead><tbody><tr><td>1</td><td></td><td>A</td></tr></tbody></table>"""


def test_both_standings_layouts_give_one_row_per_player():
    assert parse_standings(ONE_ROW) == [{"uscfId": "15346712"}, {"uscfId": None}]
    assert parse_standings(TWO_ROW) == [{"uscfId": "15680068"}, {"uscfId": None}]


@pytest.mark.parametrize("html", [PAIRINGS, "<p>no table</p>"])
def test_a_page_without_standings_raises_instead_of_counting_zero(html):
    with pytest.raises(StandingsUnreadable):
        parse_standings(html)


def test_the_tournament_list_and_an_edition_page_parse():
    events = parse_events('<a href="https://chessevents.com/event/pittsburgh/2026">Pittsburgh Open</a>'
                          '<a href="https://chessevents.com/event/pittsburgh">Pittsburgh Open</a>'
                          '<a href="https://chessevents.com/tournaments">All</a>')
    assert events == {"pittsburgh": "Pittsburgh Open"}
    base = "https://chessevents.com/event/pittsburgh/2026/standings"
    html = (f'<a href="{base}">Standings</a><a href="{base}/major">Major</a>'
            f'<a href="{base}/u2100">Under 2100</a><a href="{base}/major">Major</a>')
    assert parse_sections(html, "pittsburgh", 2026) == [("Major", f"{base}/major"),
                                                       ("Under 2100", f"{base}/u2100")]


def test_an_ended_edition_without_a_row_is_due():
    editions = [("Pittsburgh Open", 2026, date(2026, 9, 7)),
                ("Bradley Open", 2026, date(2026, 10, 12)),         # not over
                ("Atlantic Open", 2025, date(2025, 8, 10)),         # has a row
                ("Chicago Open Blitz", 2026, date(2026, 5, 24)),    # side event
                ("Chicago Open", 2024, date(2024, 5, 27))]          # before the window
    due = editions_due(editions, {("Atlantic Open", 2025)}, date(2026, 10, 4), first_year=2025)
    assert due == {("Pittsburgh Open", 2026): "Pittsburgh Open"}


def _write(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def output(tmp_path):
    _write(tmp_path / "tournament_summary.csv", ["family", "tournament_year", "final_count"],
           [["Pittsburgh Open", 2026, 170], ["Atlantic Open", 2026, 300]])
    _write(tmp_path / "tournament_metadata.csv", ["family", "year", "end_date"],
           [["Pittsburgh Open", 2026, "2026-09-07"], ["Atlantic Open", 2026, "2026-08-09"],
            ["Hartford Open", 2026, "2026-09-20"]])
    _write(tmp_path / "historical_standings.csv",
           ["tournament_name", "year", "total_players", "num_sections", "sections"],
           [["Cleveland Open", 2025, 193, 6, "{}"]])
    return tmp_path


def test_the_scrape_counts_due_editions_and_keeps_the_rest(output, monkeypatch, capsys):
    editions = {("pittsburgh", 2026): FolderEdition("pittsburgh", 2026, (
                    Section("Major", [{"uscfId": "a"}, {"uscfId": "b"}]),
                    Section("Under 1500", [{"uscfId": "c"}]))),
                ("atlantic", 2026): None}
    monkeypatch.setattr(scrape, "polite_session", lambda: None)
    monkeypatch.setattr(scrape, "read_events", lambda s: {"pittsburgh": "Pittsburgh Open",
                                                         "atlantic": "Atlantic Open"})
    monkeypatch.setattr(scrape, "read_edition", lambda s, slug, year: editions[(slug, year)])
    scrape.scrape_all(str(output), today=date(2026, 10, 4))
    with open(output / "historical_standings.csv", encoding="utf-8") as fh:
        rows = {(r["tournament_name"], r["year"]): r for r in csv.DictReader(fh)}
    assert set(rows) == {("Cleveland Open", "2025"), ("Pittsburgh Open", "2026")}
    assert (rows[("Pittsburgh Open", "2026")]["total_players"],
            rows[("Pittsburgh Open", "2026")]["source"]) == ("3", "chessevents")
    out = capsys.readouterr().out
    assert "atlantic 2026: standings not published yet" in out
    assert "no chessevents event: Hartford Open 2026" in out


def test_an_unreadable_edition_is_a_warning_and_stays_due(output, monkeypatch, capsys):
    def unreadable(session, slug, year):
        raise StandingsUnreadable("no ID column in ['Bd']")
    monkeypatch.setattr(scrape, "polite_session", lambda: None)
    monkeypatch.setattr(scrape, "read_events", lambda s: {"pittsburgh": "Pittsburgh Open"})
    monkeypatch.setattr(scrape, "read_edition", unreadable)
    scrape.scrape_all(str(output), today=date(2026, 10, 4))
    assert "WARNING: standings for pittsburgh 2026 not read" in capsys.readouterr().out
    with open(output / "historical_standings.csv", encoding="utf-8") as fh:
        assert [r["tournament_name"] for r in csv.DictReader(fh)] == ["Cleveland Open"]
