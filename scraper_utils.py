"""Compatibility shim -- implementation lives in scrapers/http.py
(2026-07-30 decomposition). Kept so the many `from scraper_utils import`
sites (scrapers, hotel_audit, structure_monitor, scrape_puzzles,
backfill_missing_data) keep working; the host-failure state stays
single-homed in scrapers.http.
"""

from scrapers.http import (  # noqa: F401
    DEAD_HOST_THRESHOLD,
    DEFAULT_TIMEOUT,
    is_host_dead,
    mark_host_failure,
    mark_host_success,
    polite_session,
    rate_limit,
    respectful_get,
)
