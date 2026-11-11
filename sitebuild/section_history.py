"""Verified section finals for events separated from a combined predecessor."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

SOURCE_FAMILY = "New York State Senior Championship With Young Adult Mi"
SECTION_FAMILIES = {
    "Senior": "New York State Senior Championship",
    "Young Adult/Middle Age": "Saratoga Tournament Of-The-Ages Open",
}
HISTORY_FILE = "section_history.json"
# Completed editions verified against the organizer's published calendars.
SOURCE_EDITIONS = {2025: ("3731", "2025-03-16"), 2026: ("4182", "2026-03-01")}


class SectionHistoryError(ValueError):
    """Unverified supplemental history cannot supply a forecast."""


def load_section_history(output_dir, summary, standings, now=None):
    """Reconcile native gross section counts with both existing source tables.

    This supplements only the metadata fallback. The combined predecessor
    remains unchanged in the training corpus, so its players are not trained
    twice. Published standings prove active counts; withdrawals complete the
    gross registration count used by the forecasting contract.
    """
    path = Path(output_dir) / HISTORY_FILE
    if not path.exists():
        return []
    now = now or datetime.now(timezone.utc)
    try:
        with path.open(encoding="utf-8") as stream:
            raw = stream.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError()
        body = json.loads(raw)
        if (not isinstance(body, dict) or set(body) != {"version", "source_family", "editions"}
                or type(body["version"]) is not int or body["version"] != 1
                or body["source_family"] != SOURCE_FAMILY
                or not isinstance(body["editions"], list) or len(body["editions"]) > 20
                or standings is None):
            raise ValueError()
        seen, result = set(), []
        def integer(n):
            return type(n) is int and 0 <= n <= 10_000
        for edition in body["editions"]:
            if (not isinstance(edition, dict) or set(edition) != {
                    "year", "tournament_id", "source_as_of", "active", "withdrawn", "total", "sections"}
                    or type(edition["year"]) is not int or edition["year"] not in SOURCE_EDITIONS
                    or edition["year"] in seen
                    or not isinstance(edition["tournament_id"], str)
                    or not re.fullmatch(r"\d{1,12}", edition["tournament_id"])
                    or not all(integer(edition[k]) for k in ["active", "withdrawn", "total"])):
                raise ValueError()
            year = edition["year"]
            seen.add(year)
            source_id, ended = SOURCE_EDITIONS[year]
            if edition["tournament_id"] != source_id:
                raise ValueError()
            observed = datetime.fromisoformat(edition["source_as_of"].replace("Z", "+00:00"))
            closed = datetime.fromisoformat(ended + "T23:59:59+00:00")
            if observed.tzinfo is None or observed > now or observed <= closed:
                raise ValueError()
            sections = edition["sections"]
            if not isinstance(sections, list) or len(sections) != len(SECTION_FAMILIES):
                raise ValueError()
            names = set()
            for section in sections:
                if (not isinstance(section, dict) or set(section) != {"name", "active", "withdrawn"}
                        or section["name"] not in SECTION_FAMILIES or section["name"] in names
                        or not integer(section["active"]) or not integer(section["withdrawn"])):
                    raise ValueError()
                names.add(section["name"])
            if (sum(s["active"] for s in sections) != edition["active"]
                    or sum(s["withdrawn"] for s in sections) != edition["withdrawn"]
                    or edition["active"] + edition["withdrawn"] != edition["total"]):
                raise ValueError()
            parent = summary[(summary["family"] == SOURCE_FAMILY) & (summary["tournament_year"] == year)]
            published = standings[(standings["tournament_name"] == SOURCE_FAMILY) & (standings["year"] == year)]
            if len(parent) != 1 or len(published) != 1 or parent.iloc[0]["final_count"] != edition["total"]:
                raise ValueError()
            counts = json.loads(published.iloc[0]["sections"])
            if (set(counts) != set(SECTION_FAMILIES)
                    or any(not integer(counts[s["name"]]) or counts[s["name"]] != s["active"] for s in sections)):
                raise ValueError()
            for section in sections:
                result.append(dict(family=SECTION_FAMILIES[section["name"]], year=year,
                                   count=section["active"] + section["withdrawn"],
                                   source_family=SOURCE_FAMILY, source_section=section["name"]))
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        raise SectionHistoryError("Verified section history unavailable or invalid") from error
