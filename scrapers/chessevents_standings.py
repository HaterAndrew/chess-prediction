"""chessevents.com standings: an edition's sections and each section's USCF IDs.

Adapter only. The pages, as served on 2026-10-04:

    /tournaments                          links /event/<slug>[/<year>], named for the event
    /event/<slug>/<year>                  links /event/<slug>/<year>/standings/<id>,
                                          named for the section
    /event/<slug>/<year>/standings/<id>   table.results-table with an "ID" or a
                                          "Name/Rating/ID" column

An edition page that is missing or redirects is an edition CCA has not
published. A standings page that does not load, or lacks the table or the
column, raises StandingsUnreadable: a layout change must stop the count,
not read as zero players. Side events and schedule lists are not fetched.
"""
import re

from bs4 import BeautifulSoup

from scraper_utils import respectful_get
from standings.count_rule import SCHEDULE_LIST_RE, Section, is_side_event_section
from standings.importer import FolderEdition
from standings.world_open import SLUG as WORLD_OPEN, world_open_family

BASE = "https://chessevents.com"
EVENT_LINK_RE = re.compile(r"/event/([a-z0-9-]+)(?:/\d{4})?/?$")
USCF_ID_RE = re.compile(r"\b(\d{8})\b")


class StandingsUnreadable(ValueError):
    """A page the count needs did not load or no longer has its layout."""


def _get(session, url):
    resp = respectful_get(session, url, allow_redirects=False)
    return resp.text if resp.status_code == 200 else None


def parse_events(html):
    """{slug: event name} from the tournament list."""
    events = {}
    for link in BeautifulSoup(html, "html.parser").find_all("a", href=EVENT_LINK_RE):
        name = link.get_text(" ", strip=True)
        if name:
            events.setdefault(EVENT_LINK_RE.search(link["href"]).group(1), name)
    return events


def parse_sections(html, slug, year):
    """[(section name, standings URL)] in page order."""
    pattern = re.compile(rf"/event/{re.escape(slug)}/{year}/standings/([^/?#]+)/?$")
    sections, seen = [], set()
    for link in BeautifulSoup(html, "html.parser").find_all("a", href=pattern):
        section_id = pattern.search(link["href"]).group(1)
        if section_id not in seen:
            seen.add(section_id)
            sections.append((link.get_text(" ", strip=True) or section_id,
                             f"{BASE}/event/{slug}/{year}/standings/{section_id}"))
    return sections


def _one_row_layout(rows, column):
    return [{"uscfId": cells[column].get_text(strip=True) or None}
            for cells in rows if len(cells) > column]


def _two_row_layout(rows, column):
    """A player's row (place, name, state) is followed by one whose place
    cell is empty and whose name cell holds rating, ID and team."""
    players = []
    for cells in rows:
        if len(cells) <= column:
            continue
        if cells[0].get_text(strip=True):
            players.append({"uscfId": None})
            continue
        found = USCF_ID_RE.search(cells[column].get_text(" ", strip=True))
        if players and found and players[-1]["uscfId"] is None:
            players[-1]["uscfId"] = found.group(1)
    return players


LAYOUTS = {"ID": _one_row_layout, "Name/Rating/ID": _two_row_layout}


def parse_standings(html):
    """[{"uscfId": id or None}] for each player of the results table. Two
    layouts are served: an "ID" column, one row per player, and a
    "Name/Rating/ID" column, two rows per player."""
    table = BeautifulSoup(html, "html.parser").find("table", class_="results-table")
    if table is None or table.thead is None or table.tbody is None:
        raise StandingsUnreadable("no results table")
    header = [c.get_text(strip=True) for c in table.thead.find_all(["th", "td"])]
    column_name = next((name for name in LAYOUTS if name in header), None)
    if column_name is None:
        raise StandingsUnreadable(f"no ID column in {header}")
    rows = [tr.find_all(["td", "th"]) for tr in table.tbody.find_all("tr")]
    return LAYOUTS[column_name](rows, header.index(column_name))


def _may_count(slug, year, name):
    if slug == WORLD_OPEN:
        return world_open_family(name, year) is not None
    return not (is_side_event_section(name) or SCHEDULE_LIST_RE.search(name))


def read_events(session):
    html = _get(session, f"{BASE}/tournaments")
    if html is None:
        raise StandingsUnreadable(f"{BASE}/tournaments did not load")
    return parse_events(html)


def read_edition(session, slug, year):
    """A FolderEdition, or None when CCA has not published the edition."""
    html = _get(session, f"{BASE}/event/{slug}/{year}")
    if html is None:
        return None
    sections = []
    for name, url in parse_sections(html, slug, year):
        if not _may_count(slug, year, name):
            continue
        page = _get(session, url)
        if page is None:
            raise StandingsUnreadable(f"{url} did not load")
        sections.append(Section(name, parse_standings(page)))
    return FolderEdition(slug, year, tuple(sections))
