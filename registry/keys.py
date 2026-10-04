"""Canonical edition keys: (canonical family, year).

The export and the scraper spell one event differently ("World Open top 6
sections" vs "2026 World Open, top 6 sections"), so any join between
tournament_summary.csv and daily_scrape.csv goes through these keys rather
than the raw names. Exact-name joins created duplicate rows (audit v5 Cat R)
and blinded 04e's truth-label guard to the World Open main events.

One function per key scheme. Each returns the edition or None when the row
carries no year; resolve() adds the family-universe check and fails loud.

Kept out of shared/ (a model source tree) and out of shared/editions.py,
which tournament_aliases imports.
"""
import re

import pandas as pd

from fees.codes import FAMILY_TO_CODE
from shared.editions import split_edition_name
from tournament_aliases import STANDINGS_NAME_MAP, canonicalize_family, cca_family

FLYER_URL_RE = re.compile(r"/([a-z]+)(\d{2})\.htm")


class UnresolvedKey(LookupError):
    """A key that names no known edition."""


class AmbiguousKey(LookupError):
    """A key that names more than one edition."""


def scrape_edition_key(name):
    """(canonical family, year) for a scraped "<year> <family>" name, or None
    when the name carries no year."""
    _, year = split_edition_name(name)
    if year is None:
        return None
    return canonicalize_family(cca_family(name)), year


def summary_edition_key(family, year):
    """(canonical family, year) for a tournament_summary row, or None when the
    row has no year."""
    if pd.isna(year):
        return None
    return canonicalize_family(str(family)), int(year)


def standings_edition_key(name, year):
    """historical_standings.csv names come from chessevents URLs
    ("Bostonchess Congress"); STANDINGS_NAME_MAP turns them into families."""
    if pd.isna(year):
        return None
    return canonicalize_family(STANDINGS_NAME_MAP.get(name, name)), int(year)


def historical_edition_key(name, year):
    """historical_tournaments.csv: the family from the "<year> <family>" name,
    the year from the row's own year column, which follows its start_date.
    Three rows carry a name year that contradicts their dates (see
    registry.exemptions)."""
    family = cca_family(name)
    if family is None or pd.isna(year):
        return None
    return canonicalize_family(family), int(year)


def _code_families(table):
    families = {}
    for family, code in table.items():
        families.setdefault(code, set()).add(canonicalize_family(family))
    return families


def fee_edition_key(url, table=None):
    """(family, year) for a chesstour flyer URL "<code><yy>.htm". Raises
    UnresolvedKey for a URL or code with no family, AmbiguousKey for a code
    that maps to two families."""
    m = FLYER_URL_RE.search(str(url))
    if not m:
        raise UnresolvedKey(f"flyer URL {url!r} has no <code><yy>.htm page")
    code, yy = m.group(1), int(m.group(2))
    families = _code_families(FAMILY_TO_CODE if table is None else table).get(code)
    if not families:
        raise UnresolvedKey(f"flyer code {code!r} maps to no family in fees/codes.py")
    if len(families) > 1:
        raise AmbiguousKey(f"flyer code {code!r} maps to {sorted(families)}")
    return families.pop(), 2000 + yy


def flyer_code(url):
    """The <code> of a flyer URL, or None."""
    m = FLYER_URL_RE.search(str(url))
    return m.group(1) if m else None
