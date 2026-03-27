"""
CLI commands for one-shot operations.

Usage:
    python -m backend.cli seed-canonical --code CCA_ACO26 --name "2026 Atlantic City Open"
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings
from backend.db.session import Base, sync_engine, SyncSessionLocal
from backend.db.models import Tournament, Entry, DailySnapshot
from backend.scraper.cca import CCAEntryScraper
from backend.scraper.cca_time import CCA_TZ, cca_day_for

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cli")


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(sync_engine)
    logger.info("Database tables created/verified")


def seed_canonical(tournament_code: str, tournament_name: str, force_canonical: bool = True):
    """Run a full canonical scrape: fetch entries, persist, create snapshot.

    Args:
        tournament_code: CCA code, e.g. "CCA_ACO26"
        tournament_name: Display name, e.g. "2026 Atlantic City Open"
        force_canonical: If True, treat this as canonical regardless of
            current time (for seeding outside the 2015 ET window).
    """
    init_db()

    # 1. Scrape
    logger.info("Scraping %s (%s)...", tournament_name, tournament_code)
    scraper = CCAEntryScraper(tournament_code)
    result = scraper.fetch_entries()
    meta = result["scrape_meta"]

    now_utc = meta["scraped_at"]
    now_et = now_utc.astimezone(CCA_TZ)
    cca_day = meta["cca_day_date"]

    logger.info(
        "Scraped %d entries | CCA-day: %s | Time: %s ET",
        meta["entry_count"],
        cca_day,
        now_et.strftime("%Y-%m-%d %I:%M %p"),
    )

    # Section breakdown
    for section, count in result["sections"].items():
        logger.info("  %-20s %d", section, count)

    # 2. Persist
    session = SyncSessionLocal()
    try:
        # Upsert tournament
        tournament = session.query(Tournament).filter_by(name=tournament_name).first()
        if not tournament:
            tournament = Tournament(name=tournament_name)
            session.add(tournament)
            session.flush()
            logger.info("Created tournament record (id=%d)", tournament.id)
        else:
            logger.info("Found existing tournament (id=%d)", tournament.id)

        tournament.last_scraped_at = now_utc
        tournament.last_entry_count = meta["entry_count"]

        # Store tournament code in metadata
        existing_meta = tournament.metadata_ or {}
        existing_meta["cca_code"] = tournament_code
        existing_meta["entry_list_url"] = scraper.entry_list_url
        existing_meta["sections_summary"] = result["sections"]
        tournament.metadata_ = existing_meta

        # Clear old entries for this CCA-day (idempotent re-runs)
        deleted = (
            session.query(Entry)
            .filter_by(tournament_id=tournament.id, cca_day_date=cca_day)
            .delete()
        )
        if deleted:
            logger.info("Cleared %d existing entries for CCA-day %s", deleted, cca_day)

        # Insert entries
        is_canonical = force_canonical or meta["is_canonical"]
        for e in result["entries"]:
            session.add(Entry(
                tournament_id=tournament.id,
                player_name=e["player_name"],
                section=e["section"],
                scraped_at=now_utc,
                cca_day_date=cca_day,
                is_canonical=is_canonical,
            ))

        # Upsert daily snapshot
        snapshot = (
            session.query(DailySnapshot)
            .filter_by(tournament_id=tournament.id, cca_day_date=cca_day)
            .first()
        )
        if snapshot:
            snapshot.entry_count = meta["entry_count"]
            snapshot.scraped_at = now_utc
            logger.info("Updated daily snapshot for %s: %d entries", cca_day, meta["entry_count"])
        else:
            session.add(DailySnapshot(
                tournament_id=tournament.id,
                cca_day_date=cca_day,
                entry_count=meta["entry_count"],
                scraped_at=now_utc,
            ))
            logger.info("Created daily snapshot for %s: %d entries", cca_day, meta["entry_count"])

        session.commit()
        logger.info("Persisted successfully")

        # 3. Summary
        total_snapshots = (
            session.query(DailySnapshot)
            .filter_by(tournament_id=tournament.id)
            .count()
        )
        print(f"\n{'='*60}")
        print(f"  {tournament_name}")
        print(f"  Entries: {meta['entry_count']}")
        print(f"  CCA-day: {cca_day}")
        print(f"  Scraped: {now_et.strftime('%b %d, %Y %I:%M %p ET')}")
        print(f"  Canonical: {is_canonical}")
        print(f"  Daily snapshots in DB: {total_snapshots}")
        print(f"{'='*60}")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Chess Entry Predictor CLI")
    sub = parser.add_subparsers(dest="command")

    seed = sub.add_parser("seed-canonical", help="Run a one-shot canonical scrape")
    seed.add_argument("--code", required=True, help="CCA tournament code (e.g. CCA_ACO26)")
    seed.add_argument("--name", required=True, help="Tournament display name")
    seed.add_argument(
        "--no-force", action="store_true",
        help="Don't force canonical flag (only mark canonical if within 2015 ET window)",
    )

    args = parser.parse_args()
    if args.command == "seed-canonical":
        seed_canonical(args.code, args.name, force_canonical=not args.no_force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
