"""Family extraction and repair (01_data_prep, verbatim)."""
import re

# Shared venue-suffix stripper so a relocated edition folds onto its history
# both here (summary build) and in tournament_aliases.canonicalize_family.
from tournament_aliases import strip_venue_suffix


def extract_family(name):
    """Strip leading year and normalize tournament family name."""
    # Remove leading year (4 digits at start)
    cleaned = re.sub(r'^\d{4}\s+', '', name)
    # Remove "on ICC" suffix (COVID-era online variants)
    cleaned = re.sub(r'\s+on ICC$', '', cleaned, flags=re.IGNORECASE)
    # Normalize "CCA " prefix removal if it appears after year strip
    cleaned = re.sub(r'^CCA\s+', '', cleaned)
    # Strip whitespace
    cleaned = cleaned.strip()
    return cleaned


def repair_family_name(name):
    """Fix known typos and normalize spacing/punctuation in family names.

    NOT the same operation as tournament_aliases.canonicalize_family, despite
    the historical shared name (renamed 2026-07-30): this is PRODUCER-side
    repair that builds the family strings stored in tournament_summary.csv —
    it deliberately does NOT fold FAMILY_GROUPS variants (pre-split "World
    Open" must stay its own family here; the aliases version folds it into
    "World Open top 6 sections" for join equality). Consumers that need
    join-time folding use tournament_aliases.canonicalize_family.
    """
    # Drop a trailing "(in <location>)" venue qualifier so a relocated edition
    # (e.g. "Eastern Class Championships (in Connecticut)") lands in the same
    # family as its prior years instead of a brand-new zero-history family.
    name = strip_venue_suffix(name)
    # Fix common typos
    name = name.replace('Championshps', 'Championships')
    name = name.replace('Championsips', 'Championships')
    name = name.replace('Cahmpionships', 'Championships')
    # AUDIT.md C6 — fix Washington Chess Congress typo merging two families
    name = name.replace('Chess Congess', 'Chess Congress')
    # Normalize whitespace: collapse multiple spaces to one
    name = re.sub(r'\s{2,}', ' ', name)
    # Normalize apostrophes
    name = name.replace('\u2019', "'").replace('\u2018', "'")
    # Normalize World Open Under 13 name variants
    if re.match(r'^World Open Under 13\b', name):
        name = 'World Open Under 13'
    # Keep "World Open top 6 sections" and "World Open lower sections" as
    # separate families (no longer consolidated into "World Open").
    # All other World Open sub-events (G/7, G/10, Blitz, Action, Women,
    # Senior, Junior, etc.) are excluded downstream.
    # Normalize Women's Championship variants
    if name == "World Open Women s Championship":
        name = "World Open Womens Championship"
    # Normalize G7/G 7 variants
    if name == "World Open G 7 Championship":
        name = "World Open G7 Championship"
    # Atlantic City Open (2026+) is a NEW tournament, NOT a rename of Atlantic Open.
    # It uses Foxwoods/Princeton as comparable family (similar size, NE open format).
    # Leave as "Atlantic City Open" — model will use FAMILY_ALIASES for ratio lookup.
    # Remove trailing whitespace
    name = name.strip()
    return name


# Known administrative entries that are not real tournaments
ADMIN_ENTRIES = {
    'Send info to CCA', 'Send payment to CCA', 'Receiving prizes electronically',
    'Prize payment', 'Send info', 'Send payment',
}


# Extract year from tournament name
def extract_year(name):
    m = re.match(r'^(\d{4})\s+', name)
    return int(m.group(1)) if m else None


def annotate_families(df):
    df['family'] = df['tournament_name'].apply(extract_family).apply(repair_family_name)

    # Filter out administrative entries
    admin_mask = df['family'].isin(ADMIN_ENTRIES)
    if admin_mask.any():
        print(f"  Filtered {admin_mask.sum()} registrations from {df[admin_mask]['family'].nunique()} admin entries")
        df = df[~admin_mask].copy()


    df['tournament_year'] = df['tournament_name'].apply(extract_year)
    return df
