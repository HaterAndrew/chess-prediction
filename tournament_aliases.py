"""
Canonical tournament family aliases — single source of truth.

Imported by scrape_entries.py (name canonicalization) and 04c_final_model.py
(historical ratio pooling). Any name mapping change goes here only.

FAMILY_GROUPS: each list is a set of names that refer to the same tournament
family. The FIRST name in each group is the canonical 2026 name when one exists.

FAMILY_ALIASES: auto-generated bidirectional map {name: [other names in group]}.

CCA_CANONICALIZE: maps scraped CCA names → canonical family name (strips year
prefix first). Only needed when CCA uses a different name than the canonical.
"""

# ── Tournament family groups ─────────────────────────────────────────────
# Each group = same tournament lineage. First entry = canonical 2026 name.
FAMILY_GROUPS = [
    # DC/Philly relocation
    ['DC Open', 'Philadelphia Open'],
    ['DC International', 'Philadelphia International'],
    # Atlantic / Foxwoods venue changes
    ['Atlantic City Open', 'Open at Foxwoods', 'Princeton Open', 'Foxwoods Open'],
    # Western Class name variants
    ['Western Class Championships', 'Western Class'],
    # World Open sub-event name variants
    ['World Open Under 13 Championship', 'World Open Under 13', 'World Open Under 13 Champ'],
    ['World Open top 6 sections', 'World Open, top 6 sections', 'World Open'],
    ['World Open lower sections', 'World Open, lower sections'],
    # NY State Scholastic name variants
    ['New York State Scholastic Championships Grades K-8', 'New York State Scholastic Championships'],
    # Southern/Southwest class name variants
    ['Southern Class Championships', 'Southern Class'],
    ['Southwest Class Championships', 'Southwest Class'],
    # Eastern variants
    ['Eastern Class Championships', 'Eastern Class'],
]

# ── Auto-generate bidirectional alias map ─────────────────────────────────
FAMILY_ALIASES = {}
for group in FAMILY_GROUPS:
    for name in group:
        others = [n for n in group if n != name]
        if others:
            FAMILY_ALIASES[name] = others

# ── CCA name → canonical family name ─────────────────────────────────────
# Applied after stripping "2026 " prefix from scraped tournament names.
# Only needed when CCA's name differs from the canonical family name.
#
# IMPORTANT: do NOT rename "Atlantic City Open" → "Atlantic Open" here.
# CCA tracks them as separate events with separate tids in daily_scrape.csv,
# 01_data_prep.py treats ACO as a NEW tournament (its own family), and the
# model pools history via FAMILY_ALIASES (lineage with Foxwoods/Princeton,
# not Atlantic Open). Renaming here corrupts metadata sync and breaks the
# tournament_name join used by reconciliation.
CCA_CANONICALIZE = {
    # CCA uses comma format; canonical uses comma format too (kept here as
    # an explicit no-op so the dict documents which names are intentionally
    # unchanged vs. simply not in the map).
    'World Open, top 6 sections': 'World Open, top 6 sections',
    'World Open, lower sections': 'World Open, lower sections',
}


def canonicalize_family(name):
    """Return the canonical family string for equality comparison.

    Matching is comma- and whitespace-insensitive. If the name is a variant
    listed in any FAMILY_GROUPS entry, returns the group's canonical (first)
    name. Otherwise returns the original name unchanged.

    Intended for unifying CSV/scrape/meta joins where historical data uses
    `World Open top 6 sections` (no comma) but CCA emits `World Open, top 6
    sections` (with comma). Pre-split `World Open` pre-2023 is treated as top
    6 per FAMILY_GROUPS.
    """
    if not isinstance(name, str):
        return name

    def _norm(s):
        return ' '.join(s.strip().replace(',', '').split())

    target = _norm(name)
    for group in FAMILY_GROUPS:
        if any(_norm(v) == target for v in group):
            return group[0]
    return name


# ── World Open exclusion — single source of truth ────────────────────────
# Sub-events that should NOT be predicted/graded as standalone tournaments.
# Used by both 04d_website_data_v2.py (filter web display) and
# 04e_performance_data.py (filter performance eval).
#
# Approach: keep an explicit allowlist of WO main events, and a regex of
# patterns to exclude. Any "World Open …" not in WO_KEEP and matching
# WO_EXCLUDE_PATTERN is dropped. New CCA variants automatically excluded
# without needing to update both call sites.
import re as _re

WO_KEEP = {
    'World Open Under 13', 'World Open Under 13 Championship',
    'World Open top 6 sections', 'World Open, top 6 sections',
    'World Open lower sections', 'World Open, lower sections',
}

# Names matching this pattern are excluded from prediction/eval. The bare
# "World Open" pre-2023 family is also excluded (superseded by top-6/lower
# split in 2023).
WO_EXCLUDE_PATTERN = _re.compile(
    r'World Open\s+(G[\s/]?\d+|Action|Womens?|Women.s|Senior|Junior|'
    r'Amateur|Blitz|Warmup|FIDE|Octos?)',
    _re.IGNORECASE,
)


def is_wo_excluded(family_name):
    """True if the family is a WO sub-event that shouldn't be predicted/graded."""
    if not isinstance(family_name, str):
        return False
    if family_name in WO_KEEP:
        return False
    if family_name == 'World Open':
        return True  # pre-2023 combined family, superseded by split
    return bool(WO_EXCLUDE_PATTERN.search(family_name))
