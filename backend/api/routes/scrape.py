"""
On-demand scrape endpoint — powers the dashboard "Refresh Entries" button.

Returns fresh entry count + ET timestamp for the "as of" display.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from zoneinfo import ZoneInfo

from backend.config import settings
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


@router.post("/{tournament_id}", response_model=ScrapeResponse)
async def scrape_now(tournament_id: str):
    """Run an on-demand scrape for a single tournament.

    Called by the dashboard "Refresh Entries" button.  Non-canonical —
    this gives the stakeholder a live count but does not overwrite
    the daily snapshot used for predictions and YoY comparisons.
    """
    try:
        scraper = CCAEntryScraper(tournament_id)
        result = scraper.fetch_entries()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scrape failed: {exc}")

    meta = result["scrape_meta"]
    scraped_utc = meta["scraped_at"]
    scraped_et = scraped_utc.astimezone(CCA_TZ)

    # TODO: persist to DB — update tournament.last_scraped_at and
    #       tournament.last_entry_count; insert entries with canonical=False

    return ScrapeResponse(
        tournament_id=tournament_id,
        entry_count=meta["entry_count"],
        cca_day_date=str(meta["cca_day_date"]),
        is_canonical=meta["is_canonical"],
        scraped_at_utc=scraped_utc.isoformat(),
        scraped_at_et=scraped_et.strftime("%b %d, %Y %I:%M %p ET"),
    )
