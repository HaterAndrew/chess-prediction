#!/usr/bin/env python3
"""
Verify current-year tournament_metadata.csv dates against public canonical
sources. Designed to prevent the class of bug where wrong event_start
dates silently compound through the T-axis, daily_data anchors, pace
alerts, and chart rendering (see git log d76ea14 for the original incident).

Source strategy:
  - Current year: chesstour.com/refs.html — single page lists every
    CCA event for the current season with per-sub-event date prefixes.
    Disambiguates World Open sub-events (top 6 / lower / U13 / etc),
    which chessevents.com lumps as one "World Open" entry.
  - Past years: chessevents.com/event/<slug>/<year> per-event pages.
    Only used when --year is set to a past year (audit mode).

Output:
  - Findings emitted as "WARNING: ..." lines on stdout so
    auto_update.py's _harvest_warnings() picks them up and writes them
    to audit_warnings.json.
  - Fetch failures emit "WARNING: source unavailable ..." rather than
    being silently skipped.
  - "INFO: ..." lines summarize totals without polluting the harvester.

Exit codes:
  - 0: success (warnings only)
  - 1: --strict and any drift > 1 day found

Run manually:
  python3 tools/verify_dates.py                       # default: current year
  python3 tools/verify_dates.py --year 2026           # specific year
  python3 tools/verify_dates.py --strict              # exit 1 on drift
  python3 tools/verify_dates.py --verbose             # show every OK row
"""
import argparse
import csv
import os
import re
import sys
from datetime import datetime, date
from typing import Optional, Iterable
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META_PATH = os.path.join(PROJECT_DIR, 'output', 'tournament_metadata.csv')

# tournament_aliases.canonicalize_family handles World Open comma/no-comma
# variants and the FAMILY_GROUPS lineage map. The verifier additionally
# strips parenthetical suffixes ("(in New Jersey)") that metadata uses to
# disambiguate venue-of-the-year for the Eastern events.
sys.path.insert(0, PROJECT_DIR)
from tournament_aliases import canonicalize_family  # noqa: E402

_PAREN_SUFFIX_RE = re.compile(r'\s*\([^)]*\)\s*$')


def _normalize_family(name: str) -> str:
    """Verifier-side normalization: canonicalize via FAMILY_GROUPS, then
    strip any trailing parenthetical suffix used for venue disambiguation."""
    name = canonicalize_family(name)
    name = _PAREN_SUFFIX_RE.sub('', name)
    return name

# Drift > 1 day fires a WARNING. Off-by-one happens occasionally when a
# CCA listing convention differs from the canonical source by a single
# day — too noisy to warn on.
DRIFT_THRESHOLD_DAYS = 1

CHESSTOUR_URL = 'https://www.chesstour.com/refs.html'

# Map canonical family name (per tournament_aliases.FAMILY_GROUPS) -> the
# substring used to identify that event in chesstour.com's listing. Pattern
# must be unique enough to avoid matching the wrong row. Update if CCA
# renames a sub-event.
CHESSTOUR_PATTERNS = {
    'Atlantic Open': 'Atlantic Open',
    'Bradley Open': 'Bradley Open',
    'Central California Open': 'Central California Open',
    'Chicago Class': 'Chicago Class Championships',
    'Chicago Open': 'Chicago Open',
    'Cleveland Open': 'Cleveland Open',
    'Continental Open': 'Continental Open',
    'DC Open': 'DC Open',
    'DC International': 'DC International',
    'Eastern Chess Congress': 'Eastern Chess Congress',
    'Eastern Class Championships': 'Eastern Class Championships',
    'Hartford Open': 'Hartford Open',
    'Indianapolis Open': 'Indianapolis Open',
    'Kings Island Open': 'Kings Island Open',
    'Los Angeles Open': 'Los Angeles Open',
    'Midwest Class Championships': 'Midwest Class Championships',
    'National Chess Congress': 'National Chess Congress',
    'New York State Championship': 'NY State Championship',
    'New York State Open': 'New York State Open And Senior Amateur',
    'North American Open': 'North American Open',
    'Pacific Coast Open': 'Pacific Coast Open',
    'Pittsburgh Open': 'Pittsburgh Open',
    'Southern Open': 'Southern Open',
    # World Open sub-events: chesstour.com lists each separately with its
    # own date prefix (unlike chessevents.com which lumps the festival).
    'World Open lower sections': 'World Open, Under 1200 and Under 1000 Sections',
    'World Open Under 13 Championship': 'World Open Under Age 13 Championship',
    'World Open top 6 sections': 'World Open, Top 6 Sections',
}

# chessevents.com slug map for past-year audit mode (--year <past>).
# Keys are canonical family names (post _normalize_family). Slugs verified by
# fetching the page and matching the <title> against the family (2026-07-30).
CHESSEVENTS_SLUGS = {
    # Pre-2026 editions of this lineage ran as the Princeton Open;
    # FAMILY_GROUPS folds Princeton Open into Atlantic City Open. No
    # atlanticcity slug exists yet — revisit when chessevents adds the
    # renamed edition.
    'Atlantic City Open': 'princeton',
    'Atlantic Open': 'atlantic',
    'Boston Chess Congress': 'boston',
    'Bradley Open': 'bradley',
    'Central California Open': 'centralcalifornia',
    'Chicago Class': 'chicagoclass',
    'Chicago Open': 'chicagoopen',
    'Cleveland Open': 'cleveland',
    'Continental Open': 'continentalopen',
    'Eastern Chess Congress': 'easternchesscongress',
    'Eastern Class Championships': 'easternclass',
    'Eastern Open': 'easternopen',
    'George Washington Open': 'georgewashington',
    'Golden State Open': 'goldenstate',
    'Hartford Open': 'hartford',
    'Indianapolis Open': 'indianapolis',
    'Kings Island Open': 'kingsisland',
    'Liberty Bell Open': 'libertybell',
    'Los Angeles Open': 'losangeles',
    'Mid-America Open': 'midamerica',
    'Midwest Class Championships': 'midwestclass',
    'National Chess Congress': 'nationalchesscongress',
    'New York State Championship': 'nychampionship',
    'New York State Open': 'newyorkopen',
    'Niagara Falls Open': 'niagarafalls',
    'North American Open': 'northamerican',
    'Pacific Coast Open': 'pacificcoast',
    'Pittsburgh Open': 'pittsburgh',
    'Southern Class Championships': 'southernclass',
    'Southern Open': 'southernopen',
    'Southwest Class Championships': 'southwestclass',
    'Western Class Championships': 'westernclass',
}

# User-Agent — chesstour.com rejects Python-urllib default with 406
HTTP_HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; chess-entry-predictor/verify_dates)'}

_MONTH_INDEX = {m: i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June',
     'July', 'August', 'September', 'October', 'November', 'December'], start=1)}
_MONTHS_RE = '|'.join(_MONTH_INDEX.keys())

# chesstour.com's secondary "(approximate dates - exact dates to be added
# closer to the tournament dates)" listing uses abbreviated month names
# (Sept, Nov, Dec, Jan...). Parse those too — events in that section are
# the canonical CCA fall/winter calendar even if dates are "approximate".
_MONTH_ABBR_INDEX = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sept': 9, 'Sep': 9, 'Oct': 10,
    'Nov': 11, 'Dec': 12,
    # 'May' is intentionally omitted: it's identical full/abbrev and is
    # already handled by the main parser. Adding it here would create
    # duplicate matches.
}
_MONTH_ABBR_RE = '|'.join(_MONTH_ABBR_INDEX.keys())

# chessevents.com per-event pages display dates as "June 13, 2025 - June 15, 2025"
CHESSEVENTS_DATE_RE = re.compile(
    rf'\b({_MONTHS_RE})\s+(\d{{1,2}}),?\s+(\d{{4}})'
)

# chesstour.com schedule entries look like:
#   "Month Dx-Dy: <listing>"          - simple range
#   "Month Dx-Month Dy: <listing>"    - cross-month
#   "Month D, Dy-Dz or Dw-Dx: <listing>" - multi-range with options
# The date prefix must be IMMEDIATELY followed (after only date-syntax
# characters: digits, dashes/en-dashes, month names, commas, " or ") by
# a colon. This prevents matching prose like "after May 8th!" where the
# colon comes much later in unrelated text.
_DATE_RANGE_TAIL = (
    # Optional main dash range: "-7" or "-July 7"
    rf'(?:\s*[-–]\s*(?:\d{{1,2}}|(?:{_MONTHS_RE})\s+\d{{1,2}}))?'
    # Zero or more comma- or "or"-prefixed alternative date specs:
    # ", 2-5", ", 2-5 or 3-5", " or 6-7"
    rf'(?:\s*(?:,\s*|\s+or\s+)\d{{1,2}}(?:\s*[-–]\s*\d{{1,2}})?)*'
    # Optional parenthetical between date and colon, e.g.
    # "July 1-5, 2-5 or 3-5 (Fourth of July Holiday Weekend):"
    rf'(?:\s*\([^)]*\))?'
)
CHESSTOUR_BLOCK_RE = re.compile(
    rf'\b(?P<month>{_MONTHS_RE})\s+(?P<day>\d{{1,2}})'
    rf'{_DATE_RANGE_TAIL}\s*:\s*'
    rf'(?P<rest>.+?)'
    rf'(?=\b(?:{_MONTHS_RE})\s+\d{{1,2}}{_DATE_RANGE_TAIL}\s*:|$)',
    re.DOTALL,
)

# Secondary "approximate dates" listing format. Compact and uniform:
# "Oct 16-18: Eastern Class Championships (IN CONNECTICUT), Windsor Locks..."
# We bound each block by the next "Abbr D[-D]:" so adjacent listings don't
# leak into each other. The year is taken from the most recent "YYYY" marker
# that precedes the match in the text (e.g. "…2026 Oct 9-11: …" or
# "2027 Jan 8-10: …").
CHESSTOUR_ABBR_BLOCK_RE = re.compile(
    rf'\b(?P<month>{_MONTH_ABBR_RE})\s+(?P<day>\d{{1,2}})'
    rf'(?:\s*[-–]\s*\d{{1,2}})?'
    rf'\s*:\s*'
    rf'(?P<rest>.+?)'
    rf'(?=\b(?:{_MONTH_ABBR_RE})\s+\d{{1,2}}(?:\s*[-–]\s*\d{{1,2}})?\s*:|$)',
    re.DOTALL,
)

# "COMING EVENTS, continued (other events to be added closer to the tournament
# dates)" header — marks the start of the secondary listing on chesstour.
# Matches the parenthetical part regardless of whether the page calls them
# "approximate dates" or "other events" (chesstour has alternated wording).
_APPROX_HEADER_RE = re.compile(
    r'\((?:approximate dates|other events)[^)]*\)', re.IGNORECASE)
# Year markers ("2026", "2027") embedded in the secondary listing.
_YEAR_MARKER_RE = re.compile(r'\b(20\d{2})\b')


def _fetch(url: str, timeout: int = 10) -> Optional[str]:
    """Fetch URL with a chesstour-compatible UA. Returns decoded text or
    None on network failure. Caller emits WARNING on None — never silent."""
    try:
        req = Request(url, headers=HTTP_HEADERS)
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        # chesstour.com declares windows-1252 in its meta; chessevents.com
        # uses utf-8. windows-1252 decode is a superset of latin-1 and
        # handles either gracefully.
        return raw.decode('windows-1252', errors='replace')
    except (URLError, HTTPError, TimeoutError, OSError):
        return None


def _strip_html(html: str) -> str:
    """Drop tags + collapse whitespace + decode common entities so a regex
    over text content works regardless of where line breaks fell in the
    Word-generated source HTML."""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = (text.replace('&nbsp;', ' ').replace('&amp;', '&')
                .replace('&bull;', '•').replace('&apos;', "'")
                .replace('&quot;', '"').replace('&#39;', "'"))
    text = re.sub(r'\s+', ' ', text)
    return text


def parse_chesstour_schedule(html: str, year: int) -> dict[str, date]:
    """Parse chesstour.com/refs.html into {family_canonical: start_date}.

    Walks every "Month Dx-...: <listing>" block and tries to match the
    listing against each known CHESSTOUR_PATTERNS substring. Only the
    first ~200 chars after the date colon are considered for matching;
    otherwise the "scroll down for other events" tail of the page lets
    one block slurp every later-mentioned event name and create false
    positives. Returns {our canonical family name: earliest start date}.
    """
    text = _strip_html(html)
    matches = list(CHESSTOUR_BLOCK_RE.finditer(text))
    out: dict[str, date] = {}
    for m in matches:
        month = m.group('month')
        day = int(m.group('day'))
        rest = m.group('rest')
        # The secondary "(approximate dates)" listing uses abbreviated
        # months (Sept, Nov, Jan) which don't trigger the full-month
        # block-boundary regex. If we see an abbrev-month date-range
        # pattern inside rest, we've leaked into the next listing —
        # truncate before it. (That listing is parsed separately by
        # parse_chesstour_abbr_schedule.)
        abbr = CHESSTOUR_ABBR_BLOCK_RE.search(rest)
        if abbr:
            rest = rest[:abbr.start()]
        # Tight matching window: the actual event name always appears
        # within the first 200 chars after the date colon. Beyond that
        # we're into venue blurbs / hotel info / cross-references.
        rest = rest[:200]
        try:
            start = date(year, _MONTH_INDEX[month], day)
        except (ValueError, KeyError):
            continue
        # Longest pattern first so "World Open, Top 6 Sections" wins
        # over a hypothetical bare "World Open".
        for family, pattern in sorted(CHESSTOUR_PATTERNS.items(),
                                       key=lambda kv: -len(kv[1])):
            if family in out:
                continue
            if pattern in rest:
                out[family] = start
                break
    # Secondary pass over the "(approximate dates)" listing for events
    # scheduled later in the year that the main schedule hasn't promoted
    # to detailed listings yet (Eastern Class, Kings Island, NCC, etc.).
    out.update(parse_chesstour_abbr_schedule(text, year, exclude=set(out.keys())))
    return out


def parse_chesstour_abbr_schedule(text: str, year: int,
                                  exclude: set[str]) -> dict[str, date]:
    """Parse the abbreviated-month secondary listing on chesstour.com.

    The page lists fall/winter events in a compact "Abbr D-D: Event, City"
    format inside an "(approximate dates …)" section. Year markers (2026,
    2027) precede the listings for each year. We only consider matches
    that appear AFTER the approximate-dates header to avoid grabbing
    abbreviated-month strings from unrelated body text.
    """
    header = _APPROX_HEADER_RE.search(text)
    if not header:
        return {}
    region = text[header.end():]
    header.end()
    # Walk year markers so a "2027 Jan 8-10: Boston" doesn't get tagged
    # with the current year. current_year tracks the most-recent marker
    # at each position.
    year_markers = [(m.start(), int(m.group(1)))
                    for m in _YEAR_MARKER_RE.finditer(region)]

    def year_at(pos: int) -> int:
        cur = year
        for marker_pos, marker_year in year_markers:
            if marker_pos <= pos:
                cur = marker_year
            else:
                break
        return cur

    out: dict[str, date] = {}
    for m in CHESSTOUR_ABBR_BLOCK_RE.finditer(region):
        month = m.group('month')
        day = int(m.group('day'))
        rest = m.group('rest')[:200]
        block_year = year_at(m.start())
        if block_year != year:
            continue
        try:
            start = date(year, _MONTH_ABBR_INDEX[month], day)
        except (ValueError, KeyError):
            continue
        for family, pattern in sorted(CHESSTOUR_PATTERNS.items(),
                                       key=lambda kv: -len(kv[1])):
            if family in exclude or family in out:
                continue
            if pattern in rest:
                out[family] = start
                break
    return out


def parse_chessevents_dates(html: str) -> tuple[Optional[date], Optional[date]]:
    """Pull (start, end) from a chessevents.com /event/<slug>/<year> page.
    Future-year pages render with an empty <h4> (event hasn't happened) —
    in that case no Month-Day-Year matches exist and we return (None, None).
    """
    matches = CHESSEVENTS_DATE_RE.findall(html)
    if len(matches) < 1:
        return None, None
    first = _to_date(matches[0])
    second = _to_date(matches[1]) if len(matches) >= 2 else None
    return first, second


def _to_date(match: tuple[str, str, str]) -> Optional[date]:
    month, day, year = match
    try:
        return date(int(year), _MONTH_INDEX[month], int(day))
    except (ValueError, KeyError):
        return None


def _load_metadata(year: int) -> list[dict]:
    with open(META_PATH) as f:
        return [r for r in csv.DictReader(f) if r.get('year') == str(year)]


def _parse_iso(s: str) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def verify_year(year: int, verbose: bool = False, fetcher=_fetch) -> tuple[int, int, int]:
    """Verify metadata against canonical sources for the given year.

    fetcher is an injection seam for tests — defaults to _fetch.

    Returns (drift_count, unavailable_count, verified_count).
    """
    rows = _load_metadata(year)
    if not rows:
        print(f'INFO: verify_dates {year}: no metadata rows for this year')
        return 0, 0, 0

    is_current = year >= datetime.now().year

    chesstour_map: dict[str, date] = {}
    # v5 follow-up: when the schedule page itself is down (or parses to zero
    # blocks), the per-event loop used to fall through the empty map and emit
    # one "source-parse failure" per future event — a transient outage on
    # 2026-07-30 produced 14 spurious per-event warnings beside the one real
    # source-unavailable line. The source-level warning already says
    # everything; per-event checks only make sense against a healthy page.
    schedule_ok = False
    if is_current:
        html = fetcher(CHESSTOUR_URL)
        if html is None:
            print(f'WARNING: source unavailable — could not fetch {CHESSTOUR_URL} '
                  '(current-year dates not verified this run)')
        else:
            chesstour_map = parse_chesstour_schedule(html, year)
            if not chesstour_map:
                print(f'WARNING: source-parse failure — '
                      f'{CHESSTOUR_URL} returned no date-listing blocks')
            else:
                schedule_ok = True

    drift = 0
    unavailable = 0
    verified = 0
    seen_families: set[str] = set()

    for row in rows:
        family = _normalize_family(row['family'])
        # v5 Cat V: metadata carries comma-variant duplicate rows ("World Open
        # lower sections" AND "World Open, lower sections") that normalize to
        # the same family — verify each family once, not once per spelling.
        if family in seen_families:
            continue
        seen_families.add(family)
        meta_start = _parse_iso(row.get('start_date', ''))
        if not meta_start:
            if verbose:
                print(f'INFO: {family} {year} has no start_date in metadata; skipping')
            continue

        # Current-year path: chesstour.com aggregate
        if is_current:
            if not schedule_ok:
                # Source down or unparseable — already warned once above. No
                # per-event print; count only families the healthy path would
                # have checked (unmapped ones skip quietly either way).
                if family in CHESSTOUR_PATTERNS:
                    unavailable += 1
                elif verbose:
                    print(f'INFO: {family} {year} has no source mapping; skipping')
                continue
            if family in chesstour_map:
                canon = chesstour_map[family]
            elif family in CHESSTOUR_PATTERNS:
                # v5 Cat V: chesstour.com's schedule page drops events once
                # they are over, so a past event missing from it is expected,
                # not a parse failure — verification is moot. A FUTURE event
                # missing from the schedule is still a real WARNING.
                event_end = _parse_iso(row.get('end_date', '')) or meta_start
                if event_end < datetime.now().date():
                    print(f'INFO: {family} {year}: event over — dropped from '
                          f'chesstour.com schedule; verification moot')
                    continue
                # We expected to find it but didn't — listing structure
                # changed or pattern is stale.
                print(f'WARNING: source-parse failure — {family} {year}: '
                      f'pattern "{CHESSTOUR_PATTERNS[family]}" not found in '
                      f'chesstour.com schedule')
                unavailable += 1
                continue
            else:
                # Family not in our verification map — skip quietly unless verbose
                if verbose:
                    print(f'INFO: {family} {year} has no source mapping; skipping')
                continue
        # Past-year path: chessevents.com per-event
        elif family in CHESSEVENTS_SLUGS:
            slug = CHESSEVENTS_SLUGS[family]
            url = f'https://chessevents.com/event/{slug}/{year}'
            html = fetcher(url)
            if html is None:
                print(f'WARNING: source unavailable — could not fetch {url} '
                      f'(for {family} {year})')
                unavailable += 1
                continue
            canon, _ = parse_chessevents_dates(html)
            if canon is None:
                print(f'WARNING: source-parse failure — {family} {year}: '
                      f'no dates on {url} (page may be a future-event placeholder)')
                unavailable += 1
                continue
        else:
            if verbose:
                print(f'INFO: {family} {year} has no source mapping; skipping')
            continue

        verified += 1
        delta = abs((canon - meta_start).days)
        if delta > DRIFT_THRESHOLD_DAYS:
            print(f'WARNING: date drift — {family} {year}: metadata={meta_start} '
                  f'canonical={canon} drift={delta} days')
            drift += 1
        elif verbose:
            print(f'OK: {family} {year}: metadata={meta_start} canonical={canon} '
                  f'(drift {delta} day{"s" if delta != 1 else ""})')

    print(f'INFO: verify_dates {year} — verified={verified}, '
          f'drift>{DRIFT_THRESHOLD_DAYS}d={drift}, source-unavailable={unavailable}')
    return drift, unavailable, verified


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Verify tournament dates against canonical sources.')
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Year to verify (default: current year)')
    parser.add_argument('--strict', action='store_true',
                        help='Exit non-zero if any drift > 1 day is found')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print every comparison, not just warnings')
    args = parser.parse_args(list(argv) if argv is not None else None)

    drift, _unavailable, _verified = verify_year(args.year, verbose=args.verbose)

    if args.strict and drift > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
