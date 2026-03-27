"""
On-demand scrape endpoint — powers the dashboard "Refresh Entries" button.

Returns fresh entry count + ET timestamp for the "as of" display.
Persists entries to DB (non-canonical) and updates tournament.last_scraped_at.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from backend.config import settings
from backend.db.models import Tournament, Entry
from backend.db.session import get_sync_db
from backend.scraper.cca import CCAEntryScraper
from backend.scraper.cca_time import CCA_TZ

router = APIRouter()


class ScrapeResponse(BaseModel):
    tournament_id: str
    entry_count: int
    cca_day_date: str
    is_canonical: bool
    scraped_at_utc: str
    scraped_at_et: str   # Human-readable ET timestamp for "as of" display


@router.post("/{tournament_code}", response_model=ScrapeResponse)
def scrape_now(tournament_code: str, db: Session = Depends(get_sync_db)):
    """Run an on-demand scrape for a single tournament.

    Called by the dashboard "Refresh Entries" button.  Non-canonical —
    this gives the stakeholder a live count but does not overwrite
    the daily snapshot used for predictions and YoY comparisons.
    """
    try:
        scraper = CCAEntryScraper(tournament_code)
        result = scraper.fetch_entries()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scrape failed: {exc}")

    meta = result["scrape_meta"]
    scraped_utc = meta["scraped_at"]
    scraped_et = scraped_utc.astimezone(CCA_TZ)

    # Persist: update tournament metadata
    tournament = (
        db.query(Tournament)
        .filter(Tournament.metadata_.contains(tournament_code))
        .first()
    )
    if tournament:
        tournament.last_scraped_at = scraped_utc
        tournament.last_entry_count = meta["entry_count"]

        # Insert entries (non-canonical)
        for e in result["entries"]:
            db.add(Entry(
                tournament_id=tournament.id,
                player_name=e["player_name"],
                section=e["section"],
                scraped_at=scraped_utc,
                cca_day_date=meta["cca_day_date"],
                is_canonical=False,
            ))

        db.commit()

    return ScrapeResponse(
        tournament_id=tournament_code,
        entry_count=meta["entry_count"],
        cca_day_date=str(meta["cca_day_date"]),
        is_canonical=meta["is_canonical"],
        scraped_at_utc=scraped_utc.isoformat(),
        scraped_at_et=scraped_et.strftime("%b %d, %Y %I:%M %p ET"),
    )
