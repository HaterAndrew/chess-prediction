"""
Celery tasks for scraping and snapshot management.

Two entry points:
  1. Scheduled: scrape_all_tournaments(canonical=True) at 2015 ET daily
  2. On-demand: scrape_tournament(id, canonical=False) from dashboard button
"""

import logging
from datetime import datetime, timezone

from backend.workers.celery_app import app
from backend.scraper.cca import CCAEntryScraper

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3, default_retry_delay=120)
def scrape_tournament(self, tournament_id: str, canonical: bool = False):
    """Scrape a single tournament's entry list.

    If canonical=True (the 2015 ET run), upsert a DailySnapshot row
    for this CCA-day so year-over-year comparisons use consistent data.
    """
    try:
        scraper = CCAEntryScraper(tournament_id)
        result = scraper.fetch_entries()
        meta = result["scrape_meta"]

        logger.info(
            "Tournament %s: %d entries | CCA-day %s | canonical=%s",
            tournament_id,
            meta["entry_count"],
            meta["cca_day_date"],
            meta["is_canonical"],
        )

        _persist_entries(tournament_id, result, canonical=canonical)

        return {
            "tournament_id": tournament_id,
            "entry_count": meta["entry_count"],
            "cca_day_date": str(meta["cca_day_date"]),
            "is_canonical": meta["is_canonical"],
            "scraped_at": meta["scraped_at"].isoformat(),
        }

    except Exception as exc:
        logger.error("Scrape failed for %s: %s", tournament_id, exc)
        raise self.retry(exc=exc)


@app.task
def scrape_all_tournaments(canonical: bool = False):
    """Fan out scrape tasks for every active tournament."""
    tournament_ids = _get_active_tournament_ids()
    for tid in tournament_ids:
        scrape_tournament.delay(tid, canonical=canonical)
    logger.info(
        "Dispatched %d scrape tasks (canonical=%s)", len(tournament_ids), canonical
    )


# ── Helpers (stubs until DB layer is wired) ──────────────────────

def _get_active_tournament_ids() -> list[str]:
    """Return IDs of tournaments that are still accepting entries.

    TODO: query the tournaments table filtered by start_date.
    """
    return []


def _persist_entries(tournament_id: str, result: dict, canonical: bool):
    """Save scraped entries and (if canonical) upsert DailySnapshot.

    TODO: wire to async DB session (sync wrapper for Celery context).
    """
    meta = result["scrape_meta"]
    logger.info(
        "Persisting %d entries for tournament %s, CCA-day %s, canonical=%s",
        meta["entry_count"],
        tournament_id,
        meta["cca_day_date"],
        canonical,
    )
