"""Resolve each file's rows to editions. Pure: frames in, results out."""
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

from registry.keys import (AmbiguousKey, UnresolvedKey, historical_edition_key,
                           scrape_edition_key, standings_edition_key, summary_edition_key)

SCHEMES = {
    "summary": summary_edition_key,
    "family_year": summary_edition_key,
    "scrape": scrape_edition_key,
    "standings": standings_edition_key,
    "historical": historical_edition_key,
}


def resolve(scheme, key, families):
    """The (family, year) edition a key names under a scheme. Raises
    UnresolvedKey when the key has no year or its family is unknown."""
    edition = SCHEMES[scheme](*key)
    if edition is None:
        raise UnresolvedKey(f"{scheme} key {key!r} carries no year")
    if edition[0] not in families:
        raise UnresolvedKey(f"{scheme} key {key!r}: no family {edition[0]!r} in the summary or metadata")
    return edition


@dataclass(frozen=True)
class Source:
    """How one file's rows map to editions.

    edition_of: row -> edition or None (may raise UnresolvedKey/AmbiguousKey)
    label: row -> the file's own key, as the registry lists it
    exemption_of: row -> the exemption rule covering it, or None
    unknown_family_rule: when set, a row of an unknown family is counted
        under this rule instead of failing (files that list every CCA event)
    unique: at most one row per edition
    column: the registry column listing this file's keys (None: not listed)
    """
    file: str
    edition_of: Callable
    label: Callable
    exemption_of: Callable = lambda row: None
    unknown_family_rule: Optional[str] = None
    unique: bool = True
    column: Optional[str] = None


@dataclass
class Resolution:
    file: str
    rows: list = field(default_factory=list)  # (edition, label)
    exempt: Counter = field(default_factory=Counter)
    unresolved: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)


def _resolve_row(source, row, families):
    """('edition', edition) | ('exempt', rule) | ('unresolved', message)."""
    rule = source.exemption_of(row)
    if rule:
        return "exempt", rule
    try:
        edition = source.edition_of(row)
    except (UnresolvedKey, AmbiguousKey) as e:
        return "unresolved", str(e)
    if edition is None:
        return "unresolved", f"{source.label(row)!r} carries no year"
    if edition[0] in families:
        return "edition", edition
    if source.unknown_family_rule:
        return "exempt", source.unknown_family_rule
    return "unresolved", f"{source.label(row)!r}: no family {edition[0]!r} in the summary or metadata"


def resolve_source(source, frame, families):
    result = Resolution(source.file)
    for i, row in enumerate(frame.to_dict("records"), start=2):
        kind, value = _resolve_row(source, row, families)
        if kind == "edition":
            result.rows.append((value, source.label(row)))
        elif kind == "exempt":
            result.exempt[value] += 1
        else:
            result.unresolved.append(f"{source.file} row {i}: {value}")
    if source.unique:
        counts = Counter(edition for edition, _ in result.rows)
        result.duplicates = [
            f"{source.file}: {family} {year} has {n} rows"
            for (family, year), n in sorted(counts.items()) if n > 1
        ]
    return result
