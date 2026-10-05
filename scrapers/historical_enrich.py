"""One tournament's row: the listing record, its entry list, and the
real-time count endpoint."""
import json
import statistics

import requests

from scraper_utils import DEFAULT_TIMEOUT, respectful_get
from scrapers.historical_entry_list import BASE_URL, fetch_entry_list_html, parse_entry_list_html
from scrapers.historical_record import (_parse_int, derive_tournament_code, extract_year,
                                        normalize_date)

REALTIME_URL = f"{BASE_URL}/tournaments/ajax_get_adv_params.php"


def fetch_realtime_count(session, tid):
    """
    Fetch real-time entry count from CCA AJAX endpoint.

    Returns dict with total, status, registered, ref_id or None.
    """
    if not tid:
        return None
    try:
        resp = respectful_get(
            session,
            REALTIME_URL,
            params={"tid": tid, "met": "0"},
            timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        text = resp.text.strip()
        parts = text.split("|")
        if len(parts) >= 4:
            return {
                "total": _parse_int(parts[0]),
                "status": parts[1].strip(),
                "registered": _parse_int(parts[2]),
                "ref_id": parts[3].strip(),
            }
        elif len(parts) >= 1:
            return {"total": _parse_int(parts[0])}
        return None
    except requests.RequestException:
        return None


def process_tournament(session, record_info):
    """
    Enrich a single tournament record with entry list and realtime data.

    Returns a dict with all extracted fields.
    """
    name = record_info.get("name", "")
    tid = record_info.get("tid", "")
    year = extract_year(record_info)
    yy = str(year)[-2:] if year else ""

    start_date = normalize_date(record_info.get("start_date", ""))
    end_date = normalize_date(record_info.get("end_date", ""))
    state = record_info.get("state", "")
    total_entries = record_info.get("total_entries", 0)

    # Derive tournament code for entry list URL
    code = derive_tournament_code(name)

    # Fetch entry list HTML (if we have code and year)
    html_data = None
    if code and yy:
        html_data = fetch_entry_list_html(session, code, yy)

    # Fetch real-time count
    rt_data = fetch_realtime_count(session, tid)

    # If realtime data has a total, prefer it over the listing total
    if rt_data and rt_data.get("total", 0) > 0:
        total_entries = max(total_entries, rt_data["total"])

    # Parse HTML entry list
    parsed = parse_entry_list_html(html_data) if html_data else {
        "sections": {},
        "schedule_dist": {},
        "player_states": [],
        "withdrawal_count": 0,
        "ratings": [],
    }

    # Compute rating statistics
    ratings = parsed["ratings"]
    rating_mean = round(statistics.mean(ratings), 1) if ratings else None
    rating_median = round(statistics.median(ratings), 1) if ratings else None
    rating_std = round(statistics.stdev(ratings), 1) if len(ratings) >= 2 else None

    # Unique states
    unique_states = len(set(parsed["player_states"])) if parsed["player_states"] else None

    return {
        "tournament_name": name,
        "year": year,
        "start_date": start_date,
        "end_date": end_date,
        "state": state,
        "total_entries": total_entries,
        "sections": json.dumps(parsed["sections"]) if parsed["sections"] else "",
        "schedule_dist": json.dumps(parsed["schedule_dist"]) if parsed["schedule_dist"] else "",
        "unique_states": unique_states if unique_states else "",
        "withdrawal_count": parsed["withdrawal_count"] if parsed["withdrawal_count"] else "",
        "rating_mean": rating_mean if rating_mean else "",
        "rating_median": rating_median if rating_median else "",
        "rating_std": rating_std if rating_std else "",
    }


def listing_only(record_info):
    """A row from the listing alone (--skip-html with --skip-realtime)."""
    return {
        "tournament_name": record_info.get("name", ""),
        "year": extract_year(record_info),
        "start_date": normalize_date(record_info.get("start_date", "")),
        "end_date": normalize_date(record_info.get("end_date", "")),
        "state": record_info.get("state", ""),
        "total_entries": record_info.get("total_entries", 0),
        "sections": "",
        "schedule_dist": "",
        "unique_states": "",
        "withdrawal_count": "",
        "rating_mean": "",
        "rating_median": "",
        "rating_std": "",
    }
