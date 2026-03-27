"""
Celery tasks for scraping and snapshot management.

Two entry points:
  1. Scheduled: scrape_all_tournaments(canonical=True) at 2015 ET daily
  2. On-demand: scrape_tournament(id, canonical=False) from dashboard button
"""

import logging
from datetime import datetime, timezone

from backend.workers.celery_app import app
from backend.db.models import Tournament, Entry, DailySnapshot
from backend.db.session import SyncSessionLocal
from backend.scraper.cca import CCAEntryScraper

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3, default_retry_delay=120)
def scrape_tournament(self, tournament_code: str, canonical: bool = False):
    """Scrape a single tournament's entry list.

    If canonical=True (the 2015 ET run), upsert a DailySnapshot row
    for this CCA-day so year-over-year comparisons use consistent data.
    """
    try:
        scraper = CCAEntryScraper(tournament_code)
        result = scraper.fetch_entries()
        meta = result["scrape_meta"]

        logger.info(
            "Tournament %s: %d entries | CCA-day %s | canonical=%s",
            tournament_code,
            meta["entry_count"],
            meta["cca_day_date"],
            canonical,
        )

        _persist_entries(tournament_code, result, canonical=canonical)

        return {
            "tournament_code": tournament_code,
            "entry_count": meta["entry_count"],
            "cca_day_date": str(meta["cca_day_date"]),
            "is_canonical": canonical,
            "scraped_at": meta["scraped_at"].isoformat(),
        }

    except Exception as exc:
        logger.error("Scrape failed for %s: %s", tournament_code, exc)
        raise self.retry(exc=exc)


@app.task
def scrape_all_tournaments(canonical: bool = False):
    """Fan out scrape tasks for every active tournament."""
    tournament_codes = _get_active_tournament_codes()
    for code in tournament_codes:
        scrape_tournament.delay(code, canonical=canonical)
    logger.info(
        "Dispatched %d scrape tasks (canonical=%s)", len(tournament_codes), canonical
    )


def _get_active_tournament_codes() -> list[str]:
    """Return CCA codes of tournaments that are still accepting entries."""
    session = SyncSessionLocal()
    try:
        tournaments = session.query(Tournament).filter(
            Tournament.metadata_.isnot(None)
        ).all()
        codes = []
        for t in tournaments:
            meta = t.metadata_ or {}
            if "cca_code" in meta:
                codes.append(meta["cca_code"])
        return codes
    finally:
        session.close()


def _persist_entries(tournament_code: str, result: dict, canonical: bool):
    """Save scraped entries and (if canonical) upsert DailySnapshot."""
    meta = result["scrape_meta"]
    session = SyncSessionLocal()

    try:
        # Find tournament by CCA code in metadata
        tournament = None
        for t in session.query(Tournament).all():
            if t.metadata_ and t.metadata_.get("cca_code") == tournament_code:
                tournament = t
                break

        if not tournament:
            logger.warning("No tournament found for code %s", tournament_code)
            return

        # Update tournament metadata
        tournament.last_scraped_at = meta["scraped_at"]
        tournament.last_entry_count = meta["entry_count"]

        # Clear old entries for this CCA-day if canonical (idempotent re-runs)
        if canonical:
            session.query(Entry).filter_by(
                tournament_id=tournament.id,
                cca_day_date=meta["cca_day_date"],
                is_canonical=True,
            ).delete()

        # Insert entries
        for e in result["entries"]:
            session.add(Entry(
                tournament_id=tournament.id,
                player_name=e["player_name"],
                section=e["section"],
                scraped_at=meta["scraped_at"],
                cca_day_date=meta["cca_day_date"],
                is_canonical=canonical,
            ))

        # Upsert daily snapshot (canonical only)
        if canonical:
            snapshot = (
                session.query(DailySnapshot)
                .filter_by(tournament_id=tournament.id, cca_day_date=meta["cca_day_date"])
                .first()
            )
            if snapshot:
                snapshot.entry_count = meta["entry_count"]
                snapshot.scraped_at = meta["scraped_at"]
            else:
                session.add(DailySnapshot(
                    tournament_id=tournament.id,
                    cca_day_date=meta["cca_day_date"],
                    entry_count=meta["entry_count"],
                    scraped_at=meta["scraped_at"],
                ))

        session.commit()
        logger.info(
            "Persisted %d entries for %s, CCA-day %s, canonical=%s",
            meta["entry_count"], tournament_code, meta["cca_day_date"], canonical,
        )

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
