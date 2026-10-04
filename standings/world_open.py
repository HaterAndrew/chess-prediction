"""World Open sections: which family each belongs to.

The worldopen folder holds the main event and a dozen separately entered
events: Under 13, Senior Amateur, Women's, Amateur, Junior and FIDE
sections, warmups, quads, hexes, blitz. Only the main sections count, so
they are listed here rather than inferred.

From 2023 CCA takes entries for the main event in two registrations, "top 6
sections" (Open, Under 2200 to Under 1400) and "lower sections", which the
summary keeps as two families. Before 2023 they are one family.
"""
import re

SLUG = "worldopen"
SPLIT_YEAR = 2023
COMBINED = "World Open"
TOP6 = "World Open top 6 sections"
LOWER = "World Open lower sections"

MAIN_SECTION_RE = re.compile(
    r"^(Open|Major|Standings|Unrated( Players|/Provisional)?|U\d{3,4}"
    r"|Under \d{3,4}( 2)?(/Unrated)?)$")
LOWER_SECTION_RE = re.compile(r"^(Under (1200|1100|1000|900|800|600)(/Unrated)?|U1200|Unrated.*)$")


def world_open_family(section_name, year):
    """The family a main section belongs to, or None for any other event."""
    name = section_name.strip()
    if not MAIN_SECTION_RE.match(name):
        return None
    if year < SPLIT_YEAR:
        return COMBINED
    return LOWER if LOWER_SECTION_RE.match(name) else TOP6
