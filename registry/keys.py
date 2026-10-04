"""Canonical edition keys: (canonical family, year).

The export and the scraper spell one event differently ("World Open top 6
sections" vs "2026 World Open, top 6 sections"), so any join between
tournament_summary.csv and daily_scrape.csv goes through these keys rather
than the raw names. Exact-name joins created duplicate rows (audit v5 Cat R)
and blinded 04e's truth-label guard to the World Open main events.

Kept out of shared/ (a model source tree) and out of shared/editions.py,
which tournament_aliases imports.
"""
import pandas as pd

from shared.editions import split_edition_name
from tournament_aliases import canonicalize_family, cca_family


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
