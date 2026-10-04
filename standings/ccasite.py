"""Read cca-site's event folders: event names, sections, and player IDs.

Adapter only. A standings row keeps its USCF ID, or its member count for a
team row, and nothing else: chess-prediction is public, and only counts
leave cca-site.

    content/events/<slug>.json              {"name", "aliases"}
    content/editions/<slug>/<year>.md       front matter: sections [{name, standings}]
    content/results/<slug>/<year>/<file>    {"rows": [{"uscfId", "members"?}]}
"""
import glob
import json
import os
import re

import yaml

from standings.count_rule import Section
from standings.importer import FolderEdition

FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.S)

# Editions whose cca-site copy lacks main sections the event had. The import
# leaves them out rather than publish a short count.
INCOMPLETE_EDITIONS = {
    ("worldopen", 2001): "3 of the 8 main sections the March 2026 archive scrape found",
    ("pittsburgh", 2026): "no Under 2100 section; chessevents.com lists it with 40 players",
}


def read_events(content_dir):
    """{slug: (name, *aliases)} for every event."""
    events = {}
    for path in sorted(glob.glob(os.path.join(content_dir, "events", "*.json"))):
        with open(path, encoding="utf-8") as fh:
            event = json.load(fh)
        slug = os.path.splitext(os.path.basename(path))[0]
        events[slug] = (event.get("name"), *(event.get("aliases") or []))
    return events


def _front_matter(path):
    with open(path, encoding="utf-8") as fh:
        match = FRONT_MATTER_RE.match(fh.read())
    if not match:
        raise ValueError(f"{path}: no front matter")
    return yaml.safe_load(match.group(1)) or {}


def _row(row):
    if "members" in row:
        return {"members": len(row["members"] or [])}
    return {"uscfId": row.get("uscfId") or None}


def _read_section(results_dir, entry):
    """A Section, or None when the standings file is absent."""
    path = os.path.join(results_dir, entry.get("standings") or "")
    if not entry.get("standings") or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)["rows"]
    return Section(str(entry["name"]).strip(), [_row(r) for r in rows])


def read_edition(content_dir, slug, year):
    meta = _front_matter(os.path.join(content_dir, "editions", slug, f"{year}.md"))
    results_dir = os.path.join(content_dir, "results", slug, str(year))
    sections, missing = [], []
    for entry in sorted(meta.get("sections") or [], key=lambda e: e.get("order", 0)):
        section = _read_section(results_dir, entry)
        if section is None:
            missing.append(str(entry["name"]).strip())
        else:
            sections.append(section)
    return FolderEdition(slug, int(year), tuple(sections), tuple(missing))


def read_editions(content_dir):
    for path in sorted(glob.glob(os.path.join(content_dir, "editions", "*", "*.md"))):
        slug = os.path.basename(os.path.dirname(path))
        year = os.path.splitext(os.path.basename(path))[0]
        if year.isdigit():
            yield read_edition(content_dir, slug, int(year))
