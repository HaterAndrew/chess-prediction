"""cca-site standings become historical_standings rows: counts only, filed
under the summary's spelling for the edition, with the cca-site filing
errors found on 2026-10-04 caught rather than counted."""
import json

import pytest

from standings.agreement import against_final_counts, compare
from standings.ccasite import read_edition, read_events
from standings.count_rule import Section
from standings.families import Folder, SpellingTie, folder_spellings, spelling_for
from standings.importer import FolderEdition, build_rows
from standings.world_open import COMBINED, LOWER, TOP6, world_open_family
from tournament_aliases import canonicalize_family


def _players(*ids):
    return [{"uscfId": i} for i in ids]


def _ids(prefix, n):
    return [f"{prefix}{i}" for i in range(n)]


# ── family spellings ─────────────────────────────────────────────────────

SPELLINGS = {"Eastern Class Championships": {2014, 2020, 2026}, "Eastern Class": {2021, 2025},
             "DC International": {2014, 2026}, "Philadelphia International": {2016, 2025}}
FOLDERS = [Folder("easternclass", ("Eastern Class Championships",)),
           Folder("dcinternational", ("DC International",)),
           Folder("international", ("Philadelphia International",)),
           Folder("bakersfield-open", ("Bakersfield Open",))]


def test_a_folder_takes_its_lineage_spellings_unless_another_folder_claims_them():
    got = folder_spellings(FOLDERS, SPELLINGS, canonicalize_family)
    assert got["easternclass"] == {"Eastern Class Championships", "Eastern Class"}
    assert got["international"] == {"Philadelphia International"}
    assert got["dcinternational"] == {"DC International"}
    assert got["bakersfield-open"] == set()


@pytest.mark.parametrize("year, expected", [
    (2023, "Eastern Class"), (2026, "Eastern Class Championships"),
    (2010, "Eastern Class Championships"),
])
def test_the_edition_takes_the_summarys_spelling_for_its_year(year, expected):
    candidates = {"Eastern Class Championships", "Eastern Class"}
    assert spelling_for(candidates, SPELLINGS, year) == expected


def test_two_spellings_in_one_year_are_a_tie():
    years = {"A Open": {2024}, "A Open (in Ohio)": {2024}}
    with pytest.raises(SpellingTie):
        spelling_for(set(years), years, 2024)


# ── World Open sections ──────────────────────────────────────────────────

@pytest.mark.parametrize("name, year, expected", [
    ("Open", 2019, COMBINED), ("Under 900", 2019, COMBINED), ("Unrated", 2019, COMBINED),
    ("Under 1400", 2024, TOP6), ("Under 1200", 2024, LOWER), ("Under 1000", 2026, LOWER),
    ("Senior Amateur", 2024, None), ("Under 13 Championship Open", 2024, None),
    ("Women's Championship", 2019, None), ("Warmup", 2019, None), ("Junior Open", 2023, None),
])
def test_world_open_main_sections_and_the_2023_split(name, year, expected):
    assert world_open_family(name, year) == expected


# ── the importer ─────────────────────────────────────────────────────────

YEARS = {"Eastern Open": {2022, 2023, 2024, 2025}, "World Open": {2019},
         "World Open top 6 sections": {2024}, "World Open lower sections": {2024},
         "National Chess Congress": {2012}, "DC International": {2014},
         "Philadelphia International": {2016}}
IMPORT_FOLDERS = [Folder("easternopen", ("Eastern Open",)), Folder("worldopen", ("World Open",)),
                  Folder("nationalchesscongress", ("National Chess Congress",)),
                  Folder("black-friday-open", ("Black Friday Open",)),
                  Folder("dcinternational", ("DC International",)),
                  Folder("international", ("Philadelphia International",))]


def _build(*editions):
    spellings = folder_spellings(IMPORT_FOLDERS, YEARS, canonicalize_family)
    return build_rows(list(editions), IMPORT_FOLDERS, spellings, YEARS)


def _totals(report):
    return {(r["tournament_name"], r["year"]): r["total_players"] for r in report.rows}


def test_a_section_holding_another_years_field_is_dropped():
    """cca-site's 2023 Eastern Open "Senior Championship" holds the 2024 field."""
    f23, f24 = _ids("a", 40), _ids("b", 50)
    report = _build(
        FolderEdition("easternopen", 2023, (Section("Premier", _players(*f23[:20])),
                                            Section("Under 1600", _players(*f23[20:])),
                                            Section("Senior Championship", _players(*f24)))),
        FolderEdition("easternopen", 2024, (Section("Premier", _players(*f24[:25])),
                                            Section("Under 1600", _players(*f24[25:])))))
    assert _totals(report) == {("Eastern Open", 2023): 40, ("Eastern Open", 2024): 50}
    assert report.dropped["re-lists the 2024 field"] == 1


def test_returning_players_are_not_a_relist():
    base = _ids("p", 30)
    report = _build(
        FolderEdition("easternopen", 2024, (Section("Premier", _players(*base[:25])),
                                            Section("Under 1600", _players(*_ids("n", 200))))),
        FolderEdition("easternopen", 2025, (Section("Premier", _players(*base)),
                                            Section("Under 1600", _players(*_ids("m", 200))))))
    assert _totals(report) == {("Eastern Open", 2024): 225, ("Eastern Open", 2025): 230}


def test_the_world_open_splits_into_its_families():
    report = _build(FolderEdition("worldopen", 2024, (
        Section("Open", _players(*_ids("o", 30))), Section("Under 1200", _players(*_ids("l", 12))),
        Section("Senior Amateur", _players(*_ids("s", 9))), Section("Blitz Open", _players("o1")))))
    assert _totals(report) == {("World Open top 6 sections", 2024): 30,
                               ("World Open lower sections", 2024): 12}
    assert report.dropped == {"separate event": 1, "side event": 1}


def test_a_section_named_for_another_event_is_that_event():
    report = _build(FolderEdition("nationalchesscongress", 2012, (
        Section("Premier", _players(*_ids("a", 50))),
        Section("Black Friday Open", _players(*_ids("b", 40))))))
    assert _totals(report) == {("National Chess Congress", 2012): 50}


def test_an_edition_filed_in_two_folders_keeps_one_row():
    sections = (Section("Open", _players(*_ids("d", 60))),)
    report = _build(FolderEdition("dcinternational", 2014, sections),
                    FolderEdition("international", 2014, sections))
    assert _totals(report) == {("DC International", 2014): 60}
    assert "filed in dcinternational/2014, international/2014" in report.notes[0]


def test_an_edition_filed_twice_with_different_counts_is_not_imported():
    report = _build(FolderEdition("dcinternational", 2014, (Section("Open", _players(*_ids("d", 60))),)),
                    FolderEdition("international", 2014, (Section("Open", _players(*_ids("d", 61))),)))
    assert report.rows == [] and "not imported" in report.notes[0]


def test_a_missing_main_section_file_keeps_the_edition_out():
    report = _build(FolderEdition("easternopen", 2024, (Section("Premier", _players("a")),),
                                  missing=("Under 1600",)))
    assert report.rows == [] and "no standings file" in report.notes[0]


def test_a_missing_side_event_file_does_not():
    report = _build(FolderEdition("easternopen", 2024, (Section("Premier", _players(*_ids("a", 20))),),
                                  missing=("Blitz",)))
    assert _totals(report) == {("Eastern Open", 2024): 20}


def test_untracked_folders_and_unplayed_editions_are_counted():
    report = _build(FolderEdition("black-friday-open", 2012, (Section("Open", _players("a")),)),
                    FolderEdition("easternopen", 2027, ()))
    assert report.rows == []
    assert (dict(report.untracked), report.without_standings) == ({"black-friday-open": 1}, 1)


def test_rows_carry_counts_and_section_names_only():
    report = _build(FolderEdition("easternopen", 2024, (Section("Premier", _players(*_ids("a", 20))),)))
    row = report.rows[0]
    assert json.loads(row["sections"]) == {"Premier": 20}
    assert (row["num_sections"], row["source"]) == (1, "ccasite")


# ── the cca-site reader ──────────────────────────────────────────────────

def _site(tmp_path):
    content = tmp_path / "content"
    (content / "events").mkdir(parents=True)
    (content / "events" / "atlantic.json").write_text(
        json.dumps({"name": "Atlantic Open", "aliases": ["Atlantic"]}), encoding="utf-8")
    (content / "editions" / "atlantic").mkdir(parents=True)
    (content / "editions" / "atlantic" / "2025.md").write_text(
        "---\nevent: atlantic\nsections:\n- {id: op, name: Open, order: 1, standings: op.standings.json}\n"
        "- {id: mx, name: Mixed Doubles Teams, order: 2, standings: mx.standings.json}\n"
        "- {id: u1, name: Under 1000, order: 3, standings: u1.standings.json}\n---\nbody\n",
        encoding="utf-8")
    results = content / "results" / "atlantic" / "2025"
    results.mkdir(parents=True)
    (results / "op.standings.json").write_text(json.dumps({"rows": [
        {"name": "A Player", "uscfId": "123", "rating": 2000}, {"name": "B Player", "uscfId": ""}]}),
        encoding="utf-8")
    (results / "mx.standings.json").write_text(json.dumps({"rows": [
        {"name": "Team", "members": [{"name": "A Player", "uscfId": "123"}, {"name": "C"}]}]}),
        encoding="utf-8")
    return content


def test_the_reader_keeps_ids_and_member_counts_only(tmp_path):
    content = _site(tmp_path)
    assert read_events(str(content)) == {"atlantic": ("Atlantic Open", "Atlantic")}
    edition = read_edition(str(content), "atlantic", 2025)
    assert edition.sections == (Section("Open", [{"uscfId": "123"}, {"uscfId": None}]),
                                Section("Mixed Doubles Teams", [{"members": 2}]))
    assert edition.missing == ("Under 1000",)


# ── agreement ────────────────────────────────────────────────────────────

def test_old_rows_pair_on_the_edition_key_and_name_sections_cca_site_lacks():
    old = [{"tournament_name": "Bostonchess Congress", "year": "2019", "total_players": "427",
            "sections": json.dumps({"Premier Section": 56, "Under 2100 Section": 60, "Blitz": 40})}]
    new = [{"tournament_name": "Boston Chess Congress", "year": 2019, "total_players": 50,
            "sections": json.dumps({"Premier": 50})}]
    pair = compare(old, new).pairs[0]
    assert (pair.key, pair.old_main, pair.new_total) == (("Boston Chess Congress", 2019), 116, 50)
    assert pair.not_in_ccasite == ("Under 2100 Section",)


def test_rows_far_from_the_final_count_are_listed():
    new = [{"tournament_name": "Chicago Open", "year": 2020, "total_players": 304},
           {"tournament_name": "Chicago Open", "year": 2019, "total_players": 914}]
    inside, outside = against_final_counts(new, {("Chicago Open", 2020): 415,
                                                 ("Chicago Open", 2019): 880})
    assert (inside, outside) == (1, [(("Chicago Open", 2020), 415, 304)])


def test_committed_rows_the_rebuild_lacks_are_kept_and_marked():
    from scripts.import_ccasite_standings import _carried, _complete
    committed = [{"tournament_name": "Bostonchess Congress", "year": "2012", "total_players": "164"},
                 {"tournament_name": "Boston", "year": "2026", "total_players": "413"},
                 {"tournament_name": "Pittsburgh Open", "year": "2026", "total_players": "160",
                  "source": "chessevents"}]
    rebuilt = [{"tournament_name": "Boston Chess Congress", "year": 2026, "total_players": 343}]
    assert [(r["tournament_name"], r["source"]) for r in _carried(committed, rebuilt)] == [
        ("Bostonchess Congress", "old scraper"), ("Pittsburgh Open", "chessevents")]
    skipped = []
    editions = [FolderEdition("pittsburgh", 2026, ()), FolderEdition("pittsburgh", 2025, ())]
    assert [e.year for e in _complete(editions, skipped)] == [2025]
    assert skipped and "Under 2100" in skipped[0]
