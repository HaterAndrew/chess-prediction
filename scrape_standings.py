"""
Scrape historical final standings from chessevents.com to build a dataset
of section-level player counts for CCA tournaments going back 20+ years.

Site structure:
  - Event page: https://chessevents.com/event/{name}/{year}
  - Standings:  https://chessevents.com/event/{name}/{year}/standings/{section}
  - Archive:    https://archive.chessevents.com/

Output: output/historical_standings.csv
  Columns: tournament_name, year, total_players, num_sections, sections
  (sections is a JSON string of {section_name: player_count} pairs)
"""

import csv
import json
import os
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "historical_standings.csv")

# Rate limit between HTTP requests (seconds)
REQUEST_DELAY = 0.5

# Session with sensible defaults
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
})

# Known major CCA tournament slugs to try across all years.
# Includes common URL-naming variations.
KNOWN_SLUGS = [
    "chicago-open",
    "chicagoopen",
    "world-open",
    "worldopen",
    "north-american-open",
    "northamericanopen",
    "liberty-bell",
    "libertybell",
    "liberty-bell-open",
    "national-chess-congress",
    "nationalchesscongress",
    "atlantic-city-open",
    "atlanticcityopen",
    "atlantic-open",
    "atlanticopen",
    "eastern-open",
    "easternopen",
    "american-open",
    "americanopen",
    "western-pacific-open",
    "westernpacificopen",
]

# Canonical display names derived from slug (first variant only)
SLUG_DISPLAY = {
    "chicago-open": "Chicago Open",
    "chicagoopen": "Chicago Open",
    "world-open": "World Open",
    "worldopen": "World Open",
    "north-american-open": "North American Open",
    "northamericanopen": "North American Open",
    "liberty-bell": "Liberty Bell",
    "libertybell": "Liberty Bell",
    "liberty-bell-open": "Liberty Bell Open",
    "national-chess-congress": "National Chess Congress",
    "nationalchesscongress": "National Chess Congress",
    "atlantic-city-open": "Atlantic City Open",
    "atlanticcityopen": "Atlantic City Open",
    "atlantic-open": "Atlantic Open",
    "atlanticopen": "Atlantic Open",
    "eastern-open": "Eastern Open",
    "easternopen": "Eastern Open",
    "american-open": "American Open",
    "americanopen": "American Open",
    "western-pacific-open": "Western Pacific Open",
    "westernpacificopen": "Western Pacific Open",
}

YEAR_RANGE = range(2003, 2027)

# Base URLs to try (main site and archive)
BASE_URLS = [
    "https://chessevents.com",
    "https://archive.chessevents.com",
]

# Archive tournament slugs (no spaces/hyphens, as used in archive index URLs)
ARCHIVE_SLUGS = [
    "chicagoopen",
    "worldopen",
    "northamericanopen",
    "libertybell",
    "atlanticopen",
    "bradleyopen",
    "clevelandopen",
    "continentalopen",
    "easternopen",
    "foxwoodsopen",
    "georgewashingtonopen",
    "goldenstate",
    "kingsislandopen",
    "losangelesopen",
    "midamericaopen",
    "midwestclass",
    "nationalchesscongress",
    "pacificcoastopen",
    "philadelphiaopen",
    "southernopen",
    "southwestclass",
    "westernclass",
    "bostonchesscongress",
]

ARCHIVE_BASE = "https://archive.chessevents.com"


def fetch(url):
    """GET a URL, return (response, soup) or (None, None) on failure."""
    try:
        resp = SESSION.get(url, timeout=20)
        time.sleep(REQUEST_DELAY)
        if resp.status_code == 200:
            # Detect redirects to the tournament list page (not an event page)
            if resp.url.rstrip("/").endswith("/tournaments"):
                print(f"  [SKIP] {url} redirected to tournament list")
                return None, None
            soup = BeautifulSoup(resp.text, "html.parser")
            return resp, soup
        return None, None
    except requests.RequestException as exc:
        print(f"  [ERROR] {url}: {exc}")
        return None, None


# Section names that are side events (not main tournament sections)
SIDE_EVENT_NAMES = {
    "blitz", "bughouse", "mixed doubles", "mixed doubles teams",
    "speed", "bullet", "rapid", "armageddon", "puzzle",
}


def discover_events_from_index():
    """
    Try to discover tournament/year combos from the site's tournament list,
    schedule page, and archive. Returns a set of (base_url, slug, year) tuples.
    """
    discovered = set()
    index_urls = [
        "https://chessevents.com/tournaments",
        "https://chessevents.com/schedule",
        "https://chessevents.com/events",
        "https://chessevents.com/",
        "https://archive.chessevents.com/",
        "https://archive.chessevents.com/tournaments",
        "https://archive.chessevents.com/events",
    ]

    # Pattern to extract slug and year from event URLs
    # e.g. /event/chicago-open/2019 or /event/chicago-open/2019/
    event_pattern = re.compile(r"/event/([a-z0-9_-]+)/(\d{4})", re.IGNORECASE)

    for idx_url in index_urls:
        print(f"[DISCOVER] Fetching {idx_url} ...")
        _, soup = fetch(idx_url)
        if soup is None:
            print(f"  -> not available")
            continue

        links = soup.find_all("a", href=True)
        count = 0
        for link in links:
            href = link["href"]
            m = event_pattern.search(href)
            if m:
                slug = m.group(1).lower()
                year = int(m.group(2))
                # Determine the base URL from the href
                if href.startswith("http"):
                    parsed = urlparse(href)
                    base = f"{parsed.scheme}://{parsed.netloc}"
                else:
                    base = idx_url.rsplit("/", 1)[0] if "/" in urlparse(idx_url).path else idx_url
                    base = f"{urlparse(idx_url).scheme}://{urlparse(idx_url).netloc}"
                discovered.add((base, slug, year))
                count += 1
        print(f"  -> found {count} event links")

    return discovered


def find_sections(base_url, slug, year):
    """
    Given an event page, find all section links for that tournament/year.
    Returns list of (section_name, section_url) tuples.
    """
    sections = []

    # Try the event page to find section/standings links
    event_urls = [
        f"{base_url}/event/{slug}/{year}",
        f"{base_url}/event/{slug}/{year}/standings",
        f"{base_url}/{slug}/{year}",
        f"{base_url}/{slug}/{year}/standings",
    ]

    visited = set()
    for event_url in event_urls:
        if event_url in visited:
            continue
        visited.add(event_url)

        _, soup = fetch(event_url)
        if soup is None:
            continue

        # Look for links to standings sections
        # Patterns: /standings/open, /standings/u2200, etc.
        standings_pattern = re.compile(
            rf"/event/{re.escape(slug)}/{year}/standings/([^/\"?#]+)",
            re.IGNORECASE,
        )
        # Also try without /event/ prefix
        standings_pattern_alt = re.compile(
            rf"/{re.escape(slug)}/{year}/standings/([^/\"?#]+)",
            re.IGNORECASE,
        )

        found_slugs = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            for pat in (standings_pattern, standings_pattern_alt):
                m = pat.search(href)
                if m:
                    sec_slug = m.group(1).strip().lower()
                    if sec_slug not in found_slugs:
                        found_slugs.add(sec_slug)
                        sec_name = link.get_text(strip=True) or sec_slug
                        # Build the full URL
                        if href.startswith("http"):
                            sec_url = href
                        else:
                            sec_url = urljoin(event_url, href)
                        sections.append((sec_name, sec_url))

        # If we found sections from the event page, also check for a
        # nav/tab list that might list sections without standings links
        if sections:
            break

        # Check if the page itself IS a standings table (single-section event)
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            # A standings table typically has header + data rows
            if len(rows) >= 3:
                # Check if it looks like a standings table (has columns
                # like Rank, Name, Rating, Score, etc.)
                header_text = table.get_text().lower()
                if any(kw in header_text for kw in ["rank", "score", "rating", "pts", "name"]):
                    sections.append(("Main", event_url))
                    break
        if sections:
            break

    return sections


def count_players_in_standings(url):
    """
    Fetch a standings page and count the number of players (table rows).
    Returns player count or 0 if unable to parse.
    """
    _, soup = fetch(url)
    if soup is None:
        return 0

    best_count = 0

    # Find all tables and pick the one that looks most like standings
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Check if this looks like a standings/results table
        header_text = ""
        thead = table.find("thead")
        first_row = rows[0] if rows else None
        if thead:
            header_text = thead.get_text().lower()
        elif first_row:
            header_text = first_row.get_text().lower()

        # Reject tables that look like a tournament list (not standings)
        tournament_list_keywords = ["start date", "end date", "most recent",
                                    "tournament name"]
        if any(kw in header_text for kw in tournament_list_keywords):
            continue

        standings_keywords = ["rank", "score", "rating", "pts", "name",
                              "player", "total", "state", "rd ", "round"]
        if not any(kw in header_text for kw in standings_keywords):
            # Also check the table's class or id
            table_attrs = " ".join([
                str(table.get("class", "")),
                str(table.get("id", "")),
            ]).lower()
            if not any(kw in table_attrs for kw in ["standing", "result",
                                                      "crosstable", "player",
                                                      "datatable"]):
                continue

        # Count data rows (exclude header rows)
        data_rows = 0
        body = table.find("tbody")
        if body:
            data_rows = len(body.find_all("tr"))
        else:
            # Skip the first row (header) and count the rest
            data_rows = len(rows) - 1

        # Filter out rows that are clearly not player rows
        # (e.g., rows with colspan, separator rows, etc.)
        if body:
            row_list = body.find_all("tr")
        else:
            row_list = rows[1:]

        actual_count = 0
        for row in row_list:
            cells = row.find_all(["td", "th"])
            # A real player row has multiple cells and some text content
            if len(cells) >= 2:
                text = row.get_text(strip=True)
                if len(text) > 2:  # not just whitespace/borders
                    actual_count += 1

        if actual_count > best_count:
            best_count = actual_count

    return best_count


def clean_section_name(raw_name):
    """Normalize section name for display."""
    name = raw_name.strip()
    # If it's just a slug, capitalize it
    if re.match(r'^[a-z0-9-]+$', name):
        name = name.replace("-", " ").title()
    # Remove redundant leading/trailing whitespace
    return name.strip()


def _archive_canonical_name(slug):
    """Derive a display name from an archive slug (no-spaces format)."""
    # Insert spaces before capital-style boundaries, then title-case
    # e.g. "chicagoopen" -> "Chicago Open", "midamericaopen" -> "Mid America Open"
    # Use SLUG_DISPLAY first if available
    if slug in SLUG_DISPLAY:
        return SLUG_DISPLAY[slug]
    # Try hyphenated form
    hyphenated = slug
    if hyphenated in SLUG_DISPLAY:
        return SLUG_DISPLAY[hyphenated]
    # Fallback: split known compound words
    # Common pattern: words ending in "open", "class", "congress", "state"
    name = slug
    for suffix in ["open", "class", "congress", "state"]:
        if name.endswith(suffix) and name != suffix:
            name = name[: -len(suffix)] + " " + suffix
            break
    return name.replace("-", " ").title()


def _extract_year_from_archive_link(href):
    """Pull the 4-digit year from an archive year-page URL path."""
    m = re.search(r"/(\d{4})/\d{2}/", href)
    if m:
        return int(m.group(1))
    return None


def count_archive_standings_players(soup):
    """
    Count player rows on an archive WordPress standings page.
    Counts <tr> tags containing at least one <td> (skips header rows with <th>).
    """
    best_count = 0
    tables = soup.find_all("table")
    for table in tables:
        data_rows = table.find_all("tr")
        count = 0
        for row in data_rows:
            # Only count rows that have <td> cells (not header rows)
            if row.find("td"):
                count += 1
        if count > best_count:
            best_count = count
    return best_count


def scrape_archive_tournaments(results, scraped):
    """
    Scrape tournament data from archive.chessevents.com WordPress pages.

    Archive URL patterns:
      Index:     /chicagoopen/
      Year page: /2015/05/chicago-open-2015/
      Standings: /2015/05/chicago-open-2015-standings-open-section/

    Appends to *results* list and *scraped* set in-place.
    """
    print("\n" + "=" * 60)
    print("PHASE 3: Scraping archive.chessevents.com tournament pages")
    print("=" * 60)

    for archive_slug in ARCHIVE_SLUGS:
        canonical = _archive_canonical_name(archive_slug)
        index_url = f"{ARCHIVE_BASE}/{archive_slug}/"
        print(f"\n[ARCHIVE] {canonical} — {index_url}")

        _, index_soup = fetch(index_url)
        if index_soup is None:
            print(f"  -> index page not available")
            continue

        # Collect year-page links from the index page.
        # Year pages live under /YYYY/MM/{slug}-YYYY/ on the archive domain.
        year_links = {}  # year -> url
        for link in index_soup.find_all("a", href=True):
            href = link["href"]
            # Absolute or relative — normalise to absolute
            full_url = urljoin(index_url, href)
            parsed = urlparse(full_url)
            # Must be on the archive domain
            if "archive.chessevents.com" not in parsed.netloc:
                continue
            year = _extract_year_from_archive_link(parsed.path)
            if year and year not in year_links:
                year_links[year] = full_url

        if not year_links:
            print(f"  -> no year pages found")
            continue

        print(f"  -> found year pages: {sorted(year_links.keys())}")

        for year in sorted(year_links):
            if (canonical, year) in scraped:
                print(f"  [{canonical} {year}] already scraped, skipping")
                continue

            year_url = year_links[year]
            print(f"\n  [{canonical} {year}] {year_url}")

            _, year_soup = fetch(year_url)
            if year_soup is None:
                print(f"    -> year page not available")
                continue

            # Find all links containing "standings" — these point to section pages
            section_links = []  # (section_name, url)
            seen_urls = set()
            for link in year_soup.find_all("a", href=True):
                href = link["href"]
                full = urljoin(year_url, href)
                if "standings" not in full.lower():
                    continue
                if full in seen_urls:
                    continue
                seen_urls.add(full)

                # Derive section name from the URL tail:
                # .../chicago-open-2015-standings-open-section/
                # -> "open-section" -> "Open Section"
                path = urlparse(full).path.rstrip("/")
                tail = path.rsplit("/", 1)[-1]  # last path component
                # Extract the part after "standings-"
                m = re.search(r"standings-(.+)$", tail, re.IGNORECASE)
                if m:
                    sec_slug = m.group(1)
                    sec_name = sec_slug.replace("-", " ").title()
                else:
                    sec_name = link.get_text(strip=True) or "Main"
                section_links.append((sec_name, full))

            if not section_links:
                print(f"    -> no standings links found on year page")
                continue

            print(f"    -> {len(section_links)} section standings page(s)")

            section_counts = {}
            for sec_name, sec_url in section_links:
                if sec_name.lower().strip() in SIDE_EVENT_NAMES:
                    print(f"       {sec_name}: skipped (side event)")
                    continue
                _, sec_soup = fetch(sec_url)
                if sec_soup is None:
                    print(f"       {sec_name}: fetch failed")
                    continue
                players = count_archive_standings_players(sec_soup)
                if players > 0:
                    section_counts[sec_name] = players
                    print(f"       {sec_name}: {players} players")
                else:
                    print(f"       {sec_name}: no player data")

            if not section_counts:
                print(f"    -> no player data for any section")
                continue

            total = sum(section_counts.values())
            print(f"    => TOTAL: {total} players across {len(section_counts)} section(s)")

            results.append({
                "tournament_name": canonical,
                "year": year,
                "total_players": total,
                "num_sections": len(section_counts),
                "sections": json.dumps(section_counts, ensure_ascii=False),
            })
            scraped.add((canonical, year))


def scrape_all():
    """Main scraping logic."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = []
    scraped = set()

    # Resume logic: load existing results, but discard clearly bad entries
    # so they get re-scraped with the fixed logic
    if os.path.exists(OUTPUT_CSV):
        discarded = 0
        with open(OUTPUT_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total = int(row["total_players"])
                # Discard entries that are obviously wrong:
                # - total_players <= 10: scraper found a nav table or single row
                # - total_players == 53: scraped the tournament list table
                if total <= 10 or total == 53:
                    discarded += 1
                    continue
                scraped.add((row["tournament_name"], int(row["year"])))
                results.append({
                    "tournament_name": row["tournament_name"],
                    "year": int(row["year"]),
                    "total_players": total,
                    "num_sections": int(row["num_sections"]),
                    "sections": row["sections"],
                })
        print(f"  Resuming: {len(scraped)} valid entries loaded, "
              f"{discarded} bad entries discarded for re-scrape", flush=True)

    # Phase 1: Discover events from index/schedule/archive pages
    print("=" * 60)
    print("PHASE 1: Discovering events from site indexes")
    print("=" * 60)
    discovered = discover_events_from_index()
    print(f"\nDiscovered {len(discovered)} event links from indexes.\n")

    # Phase 2: Build the full set of (base_url, slug, year) to try.
    # Combine discovered events with brute-force known slug/year combos.
    all_combos = set(discovered)
    for slug in KNOWN_SLUGS:
        for year in YEAR_RANGE:
            for base in BASE_URLS:
                all_combos.add((base, slug, year))

    # Deduplicate by canonical tournament name + year
    # (don't re-scrape "chicagoopen" if we already got "chicago-open" for same year)
    print("=" * 60)
    print(f"PHASE 2: Scraping standings for {len(all_combos)} slug/year/base combos")
    print("=" * 60)

    # Sort for deterministic ordering
    sorted_combos = sorted(all_combos, key=lambda x: (x[1], x[2], x[0]))

    for base_url, slug, year in sorted_combos:
        # Check if we already have this tournament/year via a different slug variant
        canonical = SLUG_DISPLAY.get(slug, slug.replace("-", " ").title())
        if (canonical, year) in scraped:
            continue

        print(f"\n[SCRAPE] {canonical} {year} ({base_url}/event/{slug}/{year})")

        sections = find_sections(base_url, slug, year)
        if not sections:
            print(f"  -> no sections found, skipping")
            continue

        print(f"  -> found {len(sections)} section(s)")

        section_counts = {}
        for sec_name, sec_url in sections:
            clean_name = clean_section_name(sec_name)
            # Skip side events (blitz, bughouse, etc.)
            if clean_name.lower() in SIDE_EVENT_NAMES:
                print(f"     {clean_name}: skipped (side event)")
                continue
            count = count_players_in_standings(sec_url)
            if count > 0:
                section_counts[clean_name] = count
                print(f"     {clean_name}: {count} players")
            else:
                print(f"     {clean_name}: no player data")

        if not section_counts:
            print(f"  -> no player data found in any section")
            continue

        total = sum(section_counts.values())
        print(f"  => TOTAL: {total} players across {len(section_counts)} section(s)")

        results.append({
            "tournament_name": canonical,
            "year": year,
            "total_players": total,
            "num_sections": len(section_counts),
            "sections": json.dumps(section_counts, ensure_ascii=False),
        })
        scraped.add((canonical, year))

    # Phase 3: Scrape archive.chessevents.com WordPress pages
    scrape_archive_tournaments(results, scraped)

    # Write output CSV
    print("\n" + "=" * 60)
    print("WRITING OUTPUT")
    print("=" * 60)

    # Sort results by tournament name, then year
    results.sort(key=lambda r: (r["tournament_name"], r["year"]))

    fieldnames = ["tournament_name", "year", "total_players", "num_sections", "sections"]
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nSaved {len(results)} tournament-year records to {OUTPUT_CSV}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total tournament-years found: {len(results)}")
    if results:
        tournaments = sorted(set(r["tournament_name"] for r in results))
        print(f"Distinct tournaments: {len(tournaments)}")
        for t in tournaments:
            t_results = [r for r in results if r["tournament_name"] == t]
            years = sorted(r["year"] for r in t_results)
            year_range = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])
            print(f"  {t}: {len(t_results)} years ({year_range})")
    else:
        print("No data found. The site structure may have changed.")
        print("Check the URLs manually and update the scraping logic.")


if __name__ == "__main__":
    scrape_all()
