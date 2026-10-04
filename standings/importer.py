"""cca-site standings to historical_standings rows: counts only.

Each folder edition splits into family editions (one, except the World
Open), each counted by standings.count_rule. Checks then run across
editions, because cca-site files are not always where they claim to be:

  * a section that re-lists another year's field is dropped. cca-site's 2023
    Eastern Open "Senior Championship" file holds the 2024 field.
  * an edition filed in two folders (international/2013-2015 and
    dcinternational/2013-2015 are both the DC International) keeps one row
    when both count the same, and none when they disagree.
  * two years of one folder with the same field are reported.
"""
import json
from collections import Counter
from dataclasses import dataclass, field

from registry.keys import standings_edition_key
from standings.count_rule import count_edition, is_side_event_section
from standings.families import SpellingTie, letters, spelling_for
from standings.world_open import SLUG as WORLD_OPEN, world_open_family

RELIST_SHARE = 0.8
MIN_EVENT_NAME_LETTERS = 8
COLUMNS = ["tournament_name", "year", "total_players", "num_sections", "sections", "source"]


@dataclass(frozen=True)
class FolderEdition:
    slug: str
    year: int
    sections: tuple             # count_rule.Section, in front-matter order
    missing: tuple = ()         # names of sections with no standings file


@dataclass
class ImportReport:
    rows: list = field(default_factory=list)
    dropped: Counter = field(default_factory=Counter)     # reason -> sections
    untracked: Counter = field(default_factory=Counter)   # slug -> editions
    without_standings: int = 0                            # editions with no files
    notes: list = field(default_factory=list)


@dataclass
class _Edition:
    slug: str
    year: int
    family: str
    sections: list
    count: object


def _ids(section):
    return {r.get("uscfId") for r in section.rows if r.get("uscfId")}


def _kept(edition):
    return [s for s in edition.sections if s.name in edition.count.kept]


def _assign(slug, year, name, family, separate_keys):
    """(family, None) for a section that counts toward one, else (None, reason)."""
    if slug == WORLD_OPEN:
        fam = world_open_family(name, year)
        if fam:
            return fam, None
        return None, "side event" if is_side_event_section(name) else "separate event"
    if any(k in letters(name) for k in separate_keys):
        return None, "separate event"
    return family, None


def _separate_keys(slug, folder_names):
    """Other events' names: a section carrying one is that event, as with
    "Black Friday Open" inside the 2012 National Chess Congress folder."""
    return {letters(n) for other, names in folder_names.items() if other != slug
            for n in names if n and len(letters(n)) >= MIN_EVENT_NAME_LETTERS}


def _family_of_folder(edition, spellings, spelling_years, report):
    if edition.slug == WORLD_OPEN:
        return WORLD_OPEN
    if not spellings.get(edition.slug):
        report.untracked[edition.slug] += 1
        return None
    try:
        return spelling_for(spellings[edition.slug], spelling_years, edition.year)
    except SpellingTie as exc:
        report.notes.append(f"{edition.slug} {edition.year}: not imported, {exc}")
        return None


def _family_editions(edition, folder_names, spellings, spelling_years, report):
    if not edition.sections:
        report.without_standings += 1     # no standings published for it
        return []
    family = _family_of_folder(edition, spellings, spelling_years, report)
    if family is None:
        return []
    separate = _separate_keys(edition.slug, folder_names)
    groups = {}
    for section in edition.sections:
        fam, reason = _assign(edition.slug, edition.year, section.name, family, separate)
        if fam is None:
            report.dropped[reason] += 1
        else:
            groups.setdefault(fam, []).append(section)
    incomplete = {_assign(edition.slug, edition.year, name, family, separate)[0]
                  for name in edition.missing if not is_side_event_section(name)}
    out = []
    for fam, sections in groups.items():
        if fam in incomplete:
            report.notes.append(f"{edition.slug} {edition.year}: {fam} not imported, "
                                "a main section has no standings file")
            continue
        out.append(_Edition(edition.slug, edition.year, fam, sections, count_edition(sections)))
    return out


def _fields(editions):
    """{(slug, year): (player IDs, number of sections) kept across its families}."""
    ids, sizes = {}, Counter()
    for e in editions:
        kept = _kept(e)
        ids.setdefault((e.slug, e.year), set()).update(*(_ids(s) for s in kept))
        sizes[(e.slug, e.year)] += len(kept)
    return ids, sizes


def _relisted_year(section, slug, year, fields):
    """The other year whose field this section mostly is, both ways round:
    a returning player base overlaps one way only."""
    ids = _ids(section)
    for (other_slug, other_year), other in fields.items():
        if other_slug != slug or other_year == year or not ids or not other:
            continue
        shared = len(ids & other)
        if shared >= RELIST_SHARE * len(ids) and shared >= RELIST_SHARE * len(other):
            return other_year
    return None


def _drop_cross_year_relists(editions, report):
    fields, sizes = _fields(editions)
    for e in editions:
        if sizes[(e.slug, e.year)] < 2:
            continue                      # a one-section year is its own field
        for section in _kept(e):
            other_year = _relisted_year(section, e.slug, e.year, fields)
            if other_year is None:
                continue
            reason = f"re-lists the {other_year} field"
            e.sections = [s for s in e.sections if s is not section]
            e.count = count_edition(e.sections)
            e.count.dropped[section.name] = reason
            report.notes.append(f"{e.slug} {e.year}: '{section.name}' ({len(section.rows)} rows) "
                                f"{reason}; dropped")


def _report_repeated_fields(editions, report):
    fields, _ = _fields(editions)
    seen = {}
    for (slug, year), ids in sorted(fields.items()):
        key = (slug, frozenset(ids))
        if ids and key in seen:
            report.notes.append(f"{slug}: {seen[key]} and {year} hold the same field")
        seen.setdefault(key, year)


def _one_per_edition(editions, report):
    by_key = {}
    for e in editions:
        by_key.setdefault(standings_edition_key(e.family, e.year), []).append(e)
    kept = []
    for (family, year), group in sorted(by_key.items()):
        where = ", ".join(f"{e.slug}/{e.year}" for e in group)
        totals = sorted({e.count.total for e in group})
        if len(totals) > 1:
            report.notes.append(f"{family} {year}: {where} count {totals}; not imported")
            continue
        first = min(group, key=lambda e: e.slug)
        if len(group) > 1:
            report.notes.append(f"{family} {year}: filed in {where}, one count; kept {first.slug}")
        kept.append(first)
    return kept


def _row(edition):
    kept = _kept(edition)
    return {"tournament_name": edition.family, "year": edition.year,
            "total_players": edition.count.total, "num_sections": len(kept),
            "sections": json.dumps({s.name: len(s.rows) for s in kept}),
            "source": "ccasite"}


def build_rows(editions, folders, spellings, spelling_years):
    """editions: FolderEdition for every cca-site folder year; folders:
    families.Folder for every cca-site event; spellings:
    families.folder_spellings(); spelling_years: {spelling: years}."""
    report = ImportReport()
    folder_names = {f.slug: f.names for f in folders}
    counted = [fe for edition in editions
               for fe in _family_editions(edition, folder_names, spellings, spelling_years, report)]
    _drop_cross_year_relists(counted, report)
    _report_repeated_fields(counted, report)
    for e in counted:
        report.dropped.update(e.count.dropped.values())
    empty = [e for e in counted if e.count.total == 0]
    for e in empty:
        report.notes.append(f"{e.slug} {e.year}: {e.family} has no main section; not imported")
    kept = _one_per_edition([e for e in counted if e.count.total > 0], report)
    report.rows = [_row(e) for e in sorted(kept, key=lambda e: (e.family, e.year))]
    return report
