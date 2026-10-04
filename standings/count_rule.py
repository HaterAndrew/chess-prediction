"""The standings count rule: unique players in an edition's main sections.

A section is dropped when it is
  * a side event, by name (blitz, quick chess, quads, extra rated games,
    team and doubles events);
  * a team section, whose rows carry `members` instead of a player;
  * a schedule list ("2-Day Major", "Under 1800 2 day"): the players on a
    shorter schedule merge into the main section and appear in its
    standings too. cca-site often has no IDs for these lists, so the
    re-listing check below cannot see it: Kings Island Open 2022's six
    2-day lists name 145 players, all of them in its main sections;
  * a re-listing: every player in it also plays in the sections kept, as
    with Eastern Open's "Senior Championship", which is its six main
    sections combined.
The kept sections' players are counted once each by USCF ID; a row without
an ID counts once.

Section names are matched here rather than with shared.side_events: that
pattern classifies whole families for the model, and widening it to
"Game/10 Open" or "Mixed Doubles" would reclassify families such as
"April Game 60" and change forecasts.
"""
import re
from dataclasses import dataclass, field

from shared.side_events import SIDE_EVENT_RE

SCHEDULE_LIST_RE = re.compile(r"\b[123]\s*-?\s*day\b", re.IGNORECASE)
SECTION_SIDE_EVENT_RE = re.compile(
    r"\bGame\s*/?\s*\d+|Mixed|Doubles|Team|Quick|Speed|Puzzle|\bQuads?\b|\bHex\b"
    r"|Extra\b.*\bGames|^Rated Games$|Fischer Random|Side Event", re.IGNORECASE)


@dataclass(frozen=True)
class Section:
    name: str
    rows: list


@dataclass
class EditionCount:
    total: int
    kept: list = field(default_factory=list)        # section names, largest first
    dropped: dict = field(default_factory=dict)     # section name -> reason


def is_side_event_section(name):
    return bool(SIDE_EVENT_RE.search(name) or SECTION_SIDE_EVENT_RE.search(name))


def _ids(section):
    return {r.get("uscfId") for r in section.rows if r.get("uscfId")}


def _drop_reason(section):
    if is_side_event_section(section.name):
        return "side event"
    if any("members" in r for r in section.rows):
        return "team section"
    if SCHEDULE_LIST_RE.search(section.name):
        return "schedule list"
    return None


def _drop_relists(sections, dropped):
    """Drop, largest first, each section whose players all play in the other
    sections still kept. Largest first, so a combined section goes before
    the sections it combines; of two identical sections one stays."""
    kept = sorted(sections, key=lambda s: len(s.rows), reverse=True)
    for section in list(kept):
        others = set().union(*(_ids(s) for s in kept if s is not section))
        ids = _ids(section)
        if ids and ids <= others:
            kept.remove(section)
            dropped[section.name] = "re-lists other sections"
    return kept


def count_edition(sections):
    dropped = {}
    main = []
    for section in sections:
        reason = _drop_reason(section)
        if reason:
            dropped[section.name] = reason
        else:
            main.append(section)
    kept = _drop_relists(main, dropped)
    ids = set().union(*(_ids(s) for s in kept)) if kept else set()
    no_id = sum(1 for s in kept for r in s.rows if not r.get("uscfId"))
    return EditionCount(len(ids) + no_id, [s.name for s in kept], dropped)
