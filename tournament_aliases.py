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

import re as _re

import re

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
    # CCA's site spells the quick-chess sub-events with a slash ("G/7"); the
    # historical lineage in summary/metadata uses the space or fused form.
    # Same events (owner-confirmed 2026-07-30) — canonical is the lineage
    # spelling the model's history is keyed on.
    ['World Open G7 Championship', 'World Open G 7 Championship', 'World Open G/7 Championship'],
    ['World Open G 10 Championship', 'World Open G/10 Championship'],
    ['World Open G 50 Championship', 'World Open G/50 Championship'],
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
    # Slash-spelled quick-chess sub-events fold onto the lineage spelling so
    # scrapers.entries.sync_metadata matches the existing metadata rows
    # instead of appending duplicate 2026 rows (same events, two spellings).
    'World Open G/7 Championship': 'World Open G7 Championship',
    'World Open G 7 Championship': 'World Open G7 Championship',
    'World Open G/10 Championship': 'World Open G 10 Championship',
    'World Open G/50 Championship': 'World Open G 50 Championship',
}


# Trailing "(in <location>)" venue qualifier. CCA titles a relocated edition
# "Eastern Class Championships (in Connecticut)" / "Eastern Chess Congress (in
# New Jersey)"; without stripping it the edition reads as a brand-new family
# with zero history and the model falls back to a flat default. Scoped to
# "(in ...)" so genuinely distinct parentheticals (e.g. "(Open Section)") stay.
_VENUE_SUFFIX_RE = re.compile(r'\s*\(\s*in\s+[^)]+\)\s*$', re.IGNORECASE)


def strip_venue_suffix(name):
    """Drop a trailing "(in <location>)" venue-relocation qualifier.

    No-op on names without that exact suffix. Single source of truth shared by
    both canonicalize_family implementations and the date verifier so a
    venue-of-the-year rename folds onto its historical series everywhere.
    """
    if not isinstance(name, str):
        return name
    return _VENUE_SUFFIX_RE.sub('', name).strip()


def canonicalize_family(name):
    """Return the canonical family string for equality comparison.

    Matching is comma- and whitespace-insensitive. A trailing "(in
    <location>)" venue qualifier is stripped first (see strip_venue_suffix).
    If the name is a variant listed in any FAMILY_GROUPS entry, returns the
    group's canonical (first) name. Otherwise returns the name unchanged.

    Intended for unifying CSV/scrape/meta joins where historical data uses
    `World Open top 6 sections` (no comma) but CCA emits `World Open, top 6
    sections` (with comma). Pre-split `World Open` pre-2023 is treated as top
    6 per FAMILY_GROUPS.
    """
    if not isinstance(name, str):
        return name

    name = strip_venue_suffix(name)

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


# ── World Open pre-split top-6 adjustments ───────────────────────────────
# Pre-2023, CCA tracked the World Open as a single tid covering all 9 sections
# (Open, U2200, U2000, U1800, U1600, U1400, U1200, U900, Unrated). Starting
# 2023 they split the registration page into "top 6 sections" (Open..U1400)
# and "lower sections" (U1200, U900). When comparing the post-split top-6
# series against pre-split editions, the bare "World Open" totals are
# apples-to-oranges: they include U1200 + U900 + Unrated.
#
# Adjusted top-6 estimates below subtract the lower sections so cross-year
# comparison is consistent. Estimates use chessevents.com final-standings
# breakdowns where available (2019, 2021) and the closest-year ratio for
# years where the archive is missing (2022).
WO_TOP6_ADJUSTED = {
    # 2019: standings Open..U1400 = 1261, U1200+U900 = 203, Unrated = 18.
    # Lower-fraction (U1200+U900+Unrated)/total = 221/1482 = 0.1491.
    # Apply to registration count 1269 → 1269 * (1 - 0.1491) = 1080.
    2019: 1080,
    # 2022: archive.chessevents.com has no 2022 World Open standings page.
    # Use 2021 lower-fraction (U1100+Unrated)/(top6+U1100+Unrated) ≈ 0.1075
    # (closest pre-split year with full breakdown).
    # Apply to registration count 1491 → 1491 * (1 - 0.1075) = 1331.
    2022: 1331,
}

# v3 N10: the top-6 fraction behind each adjusted figure above, so the
# adjustment can be applied to whatever count is actually passed in rather than
# returning a frozen literal. Each is (1 - lower_fraction) from the derivations
# documented in WO_TOP6_ADJUSTED. The literals stay as the fallback for a caller
# that passes no count.
WO_TOP6_RATIO = {
    2019: 1 - 0.1491,
    2022: 1 - 0.1075,
}


def adjust_wo_top6_count(year, count):
    """Return top-6-comparable count for a pre-split World Open year.

    Pre-2023 the bare 'World Open' family count includes lower sections
    (U1200, U900, Unrated). For year-over-year comparison against the
    explicit 2023+ 'World Open top 6 sections' tids, scale the count down
    using known final-standings ratios. Returns the original count if the
    year has no override (e.g. recent years already split at registration).

    v3 N10 (audit/AUDIT_2026-07-25.md): this used to return a hardcoded literal
    (2019 -> 1080, 2022 -> 1331) and ignore `count` entirely, so if the source
    count were ever corrected the adjusted figure would silently keep the old
    value. Store the RATIO and apply it to the count actually passed in, so the
    adjustment tracks its input.
    """
    year = int(year)
    if year not in WO_TOP6_ADJUSTED:
        return count
    ratio = WO_TOP6_RATIO.get(year)
    if ratio is None or not count:
        return WO_TOP6_ADJUSTED[year]
    return int(round(count * ratio))


# ── historical_standings.csv name → canonical family ────────────────────
# chessevents.com uses URL-derived names (lowercase concat, missing punctuation).
# Single source of truth, used by 04c_final_model.py and 06_walk_in_multipliers.py.
# AUDIT.md A2 — extend this map when validate_standings_join() reports orphans.
STANDINGS_NAME_MAP = {
    'Bostonchess Congress': 'Boston Chess Congress',
    'Midamerica Open': 'Mid-America Open',
    'Kingsisland Open': 'Kings Island Open',
    'Pacificcoast Open': 'Pacific Coast Open',
    'Losangeles Open': 'Los Angeles Open',
    'Georgewashington Open': 'George Washington Open',
    'Foxwoods Open': 'Open at Foxwoods',
    'Midwest Class': 'Midwest Class Championships',
    'Western Class': 'Western Class Championships',
    'Centralcalifornia': 'Central California Open',
    'Centralnewyork': 'Central New York Open',
    'Easternchesscongress': 'Eastern Chess Congress',
    'Easternclass': 'Eastern Class',
    'Chicagoclass': 'Chicago Class',
    'Continentalclass': 'Continental Class',
    'Continentalopen': 'Continental Open',
    'Empirestate': 'Empire State Open',
    'Empirecity': 'Empire City Open',
    'Southwest Class': 'Southwest Class Championships',
    # Single-word standings → ambiguous opens (most likely match by year+size)
    'Atlantic': 'Atlantic Open',
    'Boston': 'Boston Chess Congress',
    'Bradley': 'Bradley Open',
    'Cleveland': 'Cleveland Open',
    'Foxwoods': 'Open at Foxwoods',
    'Hartford': 'Hartford Open',
    'Indianapolis': 'Indianapolis Open',
    'Liberty Bell': 'Liberty Bell Open',
    'Manhattan': 'Manhattan Open',
    'Pittsburgh': 'Pittsburgh Open',
    'Princeton': 'Princeton Open',
    'Stamford': 'Stamford Open',
    # Lowercase-concat → spaced
    'Goldenstate': 'Golden State Open',
    'Golden State': 'Golden State Open',
    'Georgewashington': 'George Washington Open',
    'Kingsisland': 'Kings Island Open',
    'Losangeles': 'Los Angeles Open',
    'Midamerica': 'Mid-America Open',
    'Midwestclass': 'Midwest Class Championships',
    'Midwestcongress': 'Midwest Chess Congress',
    'Newyorkopen': 'New York State Open',
    'Niagarafalls': 'Niagara Falls Open',
    'Northamerican': 'North American Open',
    'Northeast': 'Northeast Open',
    'Nychampionship': 'New York State Championship',
    'Nyhighschool': 'New York State High School Championship',
    'Nyscholastics': 'New York State Scholastic Championships Grades K-8',
    'Nysenior': 'New York State Senior Championship With Young Adult Mi',
    'Pacificcoast': 'Pacific Coast Open',
    'Philadelphia': 'Philadelphia Open',
    'Southernclass': 'Southern Class Championships',
    'Southernopen': 'Southern Open',
    'Southwestclass': 'Southwest Class Championships',
    'Washingtoncongress': 'Washington Chess Congress',
    'Westernclass': 'Western Class Championships',
    'Boardwalk': 'Boardwalk Open',
    'International': 'Philadelphia International',
}


def validate_standings_join(standings_names, summary_families, verbose=True):
    """Apply STANDINGS_NAME_MAP and report standings rows that won't join to summary.

    Returns set of unmapped standings names. AUDIT.md A2 — silent drops were the
    failure mode (build_enrichment_lookup quietly skips any unmatched row).
    """
    mapped = {STANDINGS_NAME_MAP.get(n, n) for n in standings_names}
    orphans = mapped - set(summary_families)
    if verbose and orphans:
        print(f"  WARNING: {len(orphans)} standings name(s) won't join to any "
              f"summary family — extend STANDINGS_NAME_MAP in tournament_aliases.py:")
        for n in sorted(orphans):
            print(f"    {n!r}")
    return orphans
