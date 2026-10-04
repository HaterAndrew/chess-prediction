"""One completed-tournament record from the chessaction.com listing:
name, tid, dates, state, year, and the entry-list code derived from the name."""
import re
from datetime import datetime

# ── Tournament code mapping ──────────────────────────────────────────────
# CCA uses short codes in their entry list URLs. This maps known tournament
# name fragments to their URL codes. Not exhaustive — unknown tournaments
# get a best-guess derivation from their name.
KNOWN_CODES = {
    "world open": "WO",
    "chicago open": "CO",
    "national chess congress": "NCC",
    "north american open": "NAO",
    "liberty bell open": "LBO",
    "atlantic open": "AO",
    "atlantic city open": "ACO",
    "new york open": "NYO",
    "new york international": "NYI",
    "amateur team east": "ATE",
    "amateur team": "ATE",
    "mid-america open": "MAO",
    "mid america open": "MAO",
    "golden state open": "GSO",
    "pacific coast open": "PCO",
    "pittsburgh open": "PIT",
    "cleveland open": "CLEV",
    "chicago class": "CC",
    "george washington open": "GWO",
    "philadelphia open": "PHO",
    "eastern open": "EO",
    "national open": "NO",
    "las vegas open": "LVO",
    "western class": "WC",
    "los angeles open": "LAO",
    "national k-12": "NK12",
    "king of the hill": "KOH",
    "empire chess": "EC",
    "new jersey open": "NJO",
    "marshall chess": "MC",
    "bradley open": "BRAD",
    "dc international": "DCI",
    "dc open": "DCO",
    "hartford open": "HO",
    "new york state championship": "NYSC",
    "new york state open": "NYSO",
    "southern open": "SO",
    "central california open": "CCO",
    "southwest class": "SWC",
    "boston chess congress": "BCC",
}


def parse_tournament_record(record):
    """
    Parse a single tournament record from the AJAX response.

    CCA returns dicts with a single 'html' key containing embedded HTML.
    We extract: name, tid, start_date, end_date, state.
    """
    info = {}

    # CCA format: dict with 'html' key containing full HTML block
    if isinstance(record, dict) and "html" in record:
        html = record["html"]

        # Name from <a> tag text
        name_match = re.search(r'<a[^>]*>([^<]+)</a>', html)
        info["name"] = name_match.group(1).strip() if name_match else ""

        # TID from href (encoded, e.g. tid=nKGmpQ==)
        tid_match = re.search(r'tid=([A-Za-z0-9+/=]+)', html)
        info["tid"] = tid_match.group(1) if tid_match else ""

        # Dates: "Mar 13, 2026 - Mar 15, 2026"
        date_match = re.search(
            r'(\w{3}\s+\d{1,2},?\s*\d{4})\s*-\s*(\w{3}\s+\d{1,2},?\s*\d{4})', html
        )
        if date_match:
            info["start_date"] = date_match.group(1).strip()
            info["end_date"] = date_match.group(2).strip()
        else:
            info["start_date"] = ""
            info["end_date"] = ""

        # State
        state_match = re.search(r'State:\s*(\w[\w\s]*?)(?:<|&|\s*$)', html)
        info["state"] = state_match.group(1).strip() if state_match else ""

        info["total_entries"] = 0  # Will be fetched from entry list or realtime API

    elif isinstance(record, dict):
        # Fallback for structured dict format
        info["name"] = _clean_html(
            record.get("name", record.get("tournament_name", ""))
        )
        info["tid"] = str(record.get("tid", record.get("id", "")))
        info["start_date"] = record.get("start_date", "")
        info["end_date"] = record.get("end_date", "")
        info["state"] = record.get("state", "")
        info["total_entries"] = _parse_int(record.get("total", 0))

    return info


def _clean_html(text):
    """Strip HTML tags from a string."""
    text = str(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip()
    return text


def _parse_int(value):
    """Safely parse an integer from various formats."""
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace(",", "")
    match = re.search(r"(\d+)", s)
    return int(match.group(1)) if match else 0


def normalize_date(date_str):
    """Parse various date formats to YYYY-MM-DD."""
    if not date_str:
        return ""
    date_str = str(date_str).strip()

    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%b %d, %Y",
        "%b %d %Y",
        "%B %d, %Y",
        "%B %d %Y",
        "%d-%b-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def extract_year(record_info):
    """Extract tournament year from dates or name."""
    for field in ["start_date", "end_date"]:
        val = record_info.get(field, "")
        match = re.search(r"(20\d{2})", str(val))
        if match:
            return int(match.group(1))

    match = re.search(r"(20\d{2})", record_info.get("name", ""))
    if match:
        return int(match.group(1))

    return None


def derive_tournament_code(name):
    """
    Derive the CCA URL code from a tournament name.

    Tries known mappings first, then generates a code from initials.
    """
    name_lower = name.lower()
    # Strip leading year
    name_lower = re.sub(r"^\d{4}\s+", "", name_lower).strip()

    # Check known codes
    for pattern, code in KNOWN_CODES.items():
        if pattern in name_lower:
            return code

    # Generate from initials of significant words
    words = re.findall(r"[a-z]+", name_lower)
    skip = {"the", "of", "and", "in", "at", "for", "a", "an"}
    initials = "".join(w[0].upper() for w in words if w not in skip)
    return initials if initials else None
