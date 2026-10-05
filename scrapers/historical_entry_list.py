"""A tournament's chessaction.com entry list: fetch the HTML page and read
sections, schedule choices, states, withdrawals and ratings off it."""
import re
from collections import Counter

import requests

from scraper_utils import DEFAULT_TIMEOUT, respectful_get
from scrapers.historical_record import _clean_html

BASE_URL = "https://www.chessaction.com"
ENTRY_LIST_TEMPLATE = f"{BASE_URL}/tournaments/advlists/CCA/CCA_{{code}}{{yy}}/CCA_{{code}}{{yy}}_alp_n.html"


def fetch_entry_list_html(session, code, yy):
    """
    Fetch the HTML entry list for a tournament.

    Returns the HTML string or None if not found.
    """
    url = ENTRY_LIST_TEMPLATE.format(code=code, yy=yy)
    try:
        resp = respectful_get(session, url, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 200 and len(resp.text) > 200:
            return resp.text
        return None
    except requests.RequestException:
        return None


def parse_entry_list_html(html):
    """
    Parse a CCA entry list HTML page for detailed stats.

    Extracts:
      - Section breakdown (section name -> count)
      - Schedule choice distribution (3-day, 4-day, 5-day counts)
      - Player states (for geographic diversity)
      - Withdrawal count
      - USCF ratings
    """
    result = {
        "sections": {},
        "schedule_dist": {},
        "player_states": [],
        "withdrawal_count": 0,
        "ratings": [],
    }

    if not html:
        return result

    # ── Withdrawal count ──────────────────────────────────────────────
    # Pattern: "N Active Players [+M Withdrawn]" or "N Players (+M Withdrawn)"
    wd_match = re.search(
        r"(\d+)\s+Active\s+Players?\s*\[\s*\+?\s*(\d+)\s+Withdrawn\s*\]",
        html,
        re.IGNORECASE,
    )
    if not wd_match:
        wd_match = re.search(
            r"(\d+)\s+Players?\s*\(\s*\+?\s*(\d+)\s+Withdrawn\s*\)",
            html,
            re.IGNORECASE,
        )
    if wd_match:
        result["withdrawal_count"] = int(wd_match.group(2))

    # ── Section breakdown ─────────────────────────────────────────────
    # Look for section headers with counts, e.g. "Open Section (45 players)"
    # or table-based section groupings
    section_pattern = re.findall(
        r'(?:section|division)[:\s]*([^<\n(]+?)\s*[\(\[]?\s*(\d+)\s*(?:players?|entries|registered)',
        html,
        re.IGNORECASE,
    )
    if section_pattern:
        for sec_name, count in section_pattern:
            sec_name = sec_name.strip().strip(":-–")
            if sec_name:
                result["sections"][sec_name] = int(count)

    # Also try: "Section Name\n... N players" pattern in table headers
    if not result["sections"]:
        # Try to find section headers in bold/heading tags
        sec_headers = re.findall(
            r'<(?:b|strong|h[1-6])[^>]*>\s*([^<]+?(?:section|open|u\d+|under|class|reserve|premier)[^<]*?)\s*</(?:b|strong|h[1-6])>',
            html,
            re.IGNORECASE,
        )
        for header in sec_headers:
            header = _clean_html(header).strip()
            # Count rows following this header until next header
            # This is a rough heuristic — count player rows
            pattern = re.escape(header) + r'.*?(?=<(?:b|strong|h[1-6])|$)'
            block = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if block:
                player_rows = re.findall(r'\d{7,8}', block.group(0))
                if player_rows:
                    result["sections"][header] = len(player_rows)

    # ── Schedule distribution ─────────────────────────────────────────
    # Look for schedule choices like "3-Day", "4-Day", "5-Day", "2-Day"
    schedule_matches = re.findall(
        r'(\d)\s*-?\s*[Dd]ay', html
    )
    if schedule_matches:
        dist = Counter(schedule_matches)
        result["schedule_dist"] = {f"{k}-day": v for k, v in dist.items()}

    # ── Player states ─────────────────────────────────────────────────
    # CCA entry lists typically show state as 2-letter code in player rows
    # Pattern: after a USCF ID (7-8 digits), there's often a state code
    # Also try: standalone 2-letter state codes in table cells
    state_pattern = re.findall(
        r'<td[^>]*>\s*([A-Z]{2})\s*</td>', html
    )
    # Filter to valid US state codes
    valid_states = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC", "PR", "VI", "GU", "FM",
    }
    result["player_states"] = [s for s in state_pattern if s in valid_states]

    # ── USCF Ratings ──────────────────────────────────────────────────
    # Ratings are typically 3-4 digit numbers in the 100-3000 range,
    # appearing near USCF IDs (7-8 digits) in player rows
    # Look for rating patterns: a number between 100 and 2999 in table cells
    rating_candidates = re.findall(
        r'<td[^>]*>\s*(\d{3,4})\s*</td>', html
    )
    for r in rating_candidates:
        val = int(r)
        # Filter to plausible USCF rating range
        if 100 <= val <= 2999:
            result["ratings"].append(val)

    # If we got too many "ratings" relative to expected player count,
    # they might be false positives. Use a sanity check: ratings should
    # roughly equal the number of states found (both are per-player).
    n_states = len(result["player_states"])
    if n_states > 0 and len(result["ratings"]) > n_states * 3:
        # Too many — likely picking up non-rating numbers. Trim to reasonable count.
        result["ratings"] = result["ratings"][:n_states]

    return result
