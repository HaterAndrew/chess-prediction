"""An edition's standings count is its unique players in its main sections.

historical_standings.csv summed every section, so totals counted blitz and
team side events, and sections that re-list the main sections' players:
Eastern Open's "Senior Championship" (390-398 rows) is the six main
sections combined. Its walk-in ratios came out at 2.2-2.4 and the site
published walk-in totals of 590-649 against about 390 players.
"""
import pytest

from standings.count_rule import Section, count_edition, is_side_event_section


def _players(*ids):
    return [{"uscfId": i} for i in ids]


def test_side_event_section_names():
    for name in ("Blitz Championship!", "Mixed Doubles Teams!", "Blitz Open",
                 "Game/10 Open", "Saturday Night Blitz!", "G/7 Blitz", "Action",
                 "Bughouse", "Quick Chess", "Quads Quad 1", "Saturday Hex Top",
                 "Extra Rated Games", "extra rated games", "Rated Games",
                 "Fischer Random", "Under 2300 (Side Event)"):
        assert is_side_event_section(name), name
    for name in ("Premier Section!", "Under 2200", "Under 1000 Section", "Open",
                 "Senior Championship!", "Under 13 Championship Open"):
        assert not is_side_event_section(name), name


def test_a_section_that_relists_the_main_sections_is_dropped():
    sections = [
        Section("Premier", _players("a", "b")),
        Section("Under 1600", _players("c", "d", "e")),
        Section("Senior Championship!", _players("a", "b", "c", "d", "e")),
        Section("Blitz Championship!", _players("a", "x")),
    ]
    result = count_edition(sections)
    assert result.total == 5
    assert result.kept == ["Under 1600", "Premier"]
    assert result.dropped == {"Senior Championship!": "re-lists other sections",
                              "Blitz Championship!": "side event"}


def test_team_sections_are_dropped():
    team = Section("Pairs Championship", [{"members": [{"uscfId": "a"}, {"uscfId": "z"}]}])
    result = count_edition([Section("Open", _players("a", "b")), team])
    assert (result.total, result.dropped) == (2, {"Pairs Championship": "team section"})


def test_players_are_counted_once_across_sections_and_reentries():
    result = count_edition([Section("U1400", _players("a", "a", "b")),
                            Section("U1600", _players("b", "c"))])
    assert result.total == 3


def test_rows_without_an_id_count_once_each():
    result = count_edition([Section("Open", [{"uscfId": ""}, {"uscfId": None}, {"uscfId": "a"}])])
    assert result.total == 3


def test_two_identical_sections_keep_one():
    result = count_edition([Section("A", _players("a", "b")), Section("B", _players("a", "b"))])
    assert result.total == 2 and len(result.kept) == 1


def test_an_edition_with_no_main_section_counts_zero():
    result = count_edition([Section("Blitz", _players("a"))])
    assert result.total == 0 and result.kept == []


@pytest.mark.parametrize("ids", [[], ["", None]])
def test_a_section_without_ids_is_never_judged_a_relist(ids):
    result = count_edition([Section("Open", _players("a", "b")),
                            Section("Under 1000", [{"uscfId": i} for i in ids])])
    assert "Under 1000" not in result.dropped


def test_schedule_lists_are_dropped_even_without_ids():
    """cca-site has no IDs for Kings Island Open 2022's 2-day lists; all 145
    of their players are in the main sections too."""
    result = count_edition([Section("Under 1700", _players("a", "b", "c")),
                            Section("Under 1700 2-Day", [{"uscfId": None}] * 2),
                            Section("2-Day Major!", [{"uscfId": None}]),
                            Section("Under 1200 2 day", _players("c"))])
    assert result.total == 3
    assert set(result.dropped.values()) == {"schedule list"}
