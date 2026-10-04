"""Which family spelling a cca-site event folder's edition is filed under.

Rows are named with the spelling the summary uses for that edition, so the
letters-only join in 06_walk_in_multipliers and the model's family lookup
find them: CCA renamed "Eastern Class Championships" to "Eastern Class" for
2021-2025 and back for 2026, and the summary follows each year's card.

A folder's spellings are those whose letters match its cca-site name, an
alias, or the name the standings scraper gave it, plus the other spellings
of the same family that no other folder claims. The second clause keeps
"DC International" with the dcinternational folder although the
international folder (Philadelphia International) shares its lineage.
"""
import re
from dataclasses import dataclass

from tournament_aliases import STANDINGS_NAME_MAP


def letters(name):
    return re.sub(r"[^a-z]", "", str(name).casefold())


@dataclass(frozen=True)
class Folder:
    slug: str
    names: tuple   # cca-site name, its aliases, the scraper's mapped name


def legacy_standings_name(slug):
    """The family STANDINGS_NAME_MAP gives the name the old scraper filed a
    chessevents slug under ("newyorkopen" -> "Newyorkopen" -> "New York
    State Open"), or None."""
    return STANDINGS_NAME_MAP.get(slug.replace("-", " ").title())


class SpellingTie(ValueError):
    """Two spellings of one folder both have a row in the edition's year."""


def _name_matches(folder, spellings):
    keys = {letters(n) for n in folder.names if n}
    return {s for s in spellings if letters(s) in keys}


def folder_spellings(folders, spelling_years, canonical):
    """{slug: spellings}. An empty set means the folder is outside the
    tracked families."""
    spellings = set(spelling_years)
    claimed = {f.slug: _name_matches(f, spellings) for f in folders}
    owners = {}
    for slug, found in claimed.items():
        for spelling in found:
            owners.setdefault(spelling, set()).add(slug)
    out = {}
    for slug, found in claimed.items():
        families = {canonical(s) for s in found}
        lineage = {s for s in spellings
                   if canonical(s) in families and owners.get(s, {slug}) == {slug}}
        out[slug] = found | lineage
    return out


def spelling_for(candidates, spelling_years, year):
    """The candidate with a row nearest the year; on equal distance the
    later row wins (a renamed card keeps its new name)."""
    def distance(spelling):
        return min((abs(y - year), -y) for y in spelling_years[spelling])
    ranked = sorted(candidates, key=lambda s: (distance(s), s))
    if len(ranked) > 1 and distance(ranked[0]) == distance(ranked[1]):
        raise SpellingTie(f"{ranked[0]!r} and {ranked[1]!r} both name the {year} edition")
    return ranked[0]
