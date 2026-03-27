"""
CCA entry list scraper.

Scrapes Continental Chess Association advance entry lists from
onlineregistration.cc.  Entry lists are pre-generated static HTML files
at a predictable path:
    advlists/CCA/{tournament_code}/{tournament_code}_alp_n.html

Assigns each scrape to the correct CCA-day and flags canonical
(post-close) pulls.
"""

import logging
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from backend.scraper.cca_time import CCA_TZ, cca_day_for, is_canonical_window

logger = logging.getLogger(__name__)

BASE_URL = "https://onlineregistration.cc/tournaments"


class CCAEntryScraper:
    """Scrapes Continental Chess Association entry list pages."""

    def __init__(self, tournament_code: str, session_cookies: dict | None = None):
        """
        Args:
            tournament_code: CCA tournament code, e.g. "CCA_ACO26" for
                Atlantic City Open 2026.  Used to construct the entry
                list URL.
        """
        self.tournament_code = tournament_code
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ChessEntryPredictor/0.1",
        })
        if session_cookies:
            self.session.cookies.update(session_cookies)

    @property
    def entry_list_url(self) -> str:
        code = self.tournament_code
        return f"{BASE_URL}/advlists/CCA/{code}/{code}_alp_n.html"

    def fetch_entries(self) -> dict:
        """Fetch current entry list and annotate with CCA-day metadata.

        Returns:
            {
                "entries": [{"player_name", "section", "uscf_id",
                             "uscf_rating", "state", "schedule"}, ...],
                "sections": {"Open": 76, "Under 2200": 42, ...},
                "scrape_meta": {
                    "scraped_at": datetime (UTC),
                    "cca_day_date": date,
                    "is_canonical": bool,
                    "entry_count": int,
                },
            }
        """
        now_utc = datetime.now(timezone.utc)

        resp = self.session.get(self.entry_list_url, timeout=30)
        resp.raise_for_status()

        entries, sections = self._parse_entry_table(resp.text)

        return {
            "entries": entries,
            "sections": sections,
            "scrape_meta": {
                "scraped_at": now_utc,
                "cca_day_date": cca_day_for(now_utc),
                "is_canonical": is_canonical_window(now_utc),
                "entry_count": len(entries),
            },
        }

    def _parse_entry_table(self, html: str) -> tuple[list[dict], dict]:
        """Extract player entries and section counts from CCA HTML.

        CCA entry list structure:
          - Table 0: section summary (section names in row 1, counts in row 2)
          - Table 2 (or largest): player rows with columns:
            Name | Name (alt) | FIDE ID | FIDE Rating | USCF ID |
            USCF Rating | State | Section | Schedule | Bye(s)
        """
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        entries = []
        sections = {}

        if not tables:
            logger.warning("No tables found on entry list page")
            return entries, sections

        # Parse section summary from first table
        if len(tables) >= 1:
            summary_rows = tables[0].find_all("tr")
            if len(summary_rows) >= 3:
                header_cells = summary_rows[1].find_all("td")
                count_cells = summary_rows[2].find_all("td")
                for hc, cc in zip(header_cells, count_cells):
                    section_name = hc.get_text(strip=True)
                    count_text = cc.get_text(strip=True)
                    # Count format: "76" or "76[+3 W]" (waitlist)
                    match = re.match(r"(\d+)", count_text)
                    if match and section_name:
                        sections[section_name] = int(match.group(1))

        # Parse player rows from the main table
        # Find the table with the "success" header row
        player_table = None
        for t in tables:
            if t.find("tr", class_="success"):
                player_table = t
                break
        if not player_table:
            # Fallback: largest table
            player_table = max(tables, key=lambda t: len(t.find_all("tr")))

        rows = player_table.find_all("tr")
        for row in rows:
            cls = " ".join(row.get("class", []))
            if "success" in cls:
                continue  # Header row

            cols = row.find_all("td")
            if len(cols) < 8:
                continue

            name = cols[0].get_text(strip=True)
            if not name or name.lower().startswith(("player", "name", "filter")):
                continue

            entries.append({
                "player_name": name,
                "fide_id": cols[2].get_text(strip=True) or None,
                "fide_rating": cols[3].get_text(strip=True) or None,
                "uscf_id": cols[4].get_text(strip=True) or None,
                "uscf_rating": cols[5].get_text(strip=True) or None,
                "state": cols[6].get_text(strip=True) or None,
                "section": cols[7].get_text(strip=True) or None,
                "schedule": cols[8].get_text(strip=True) if len(cols) > 8 else None,
            })

        logger.info(
            "Parsed %d entries for %s | sections: %s",
            len(entries),
            self.tournament_code,
            sections,
        )
        return entries, sections
