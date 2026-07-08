#!/usr/bin/env python3
"""
Fetch 10 difficult chess puzzles daily from the Lichess puzzle database.

Workflow:
  1. If output/puzzle_bank.csv doesn't exist (or has < 5000 rows),
     stream-download the Lichess puzzle DB CSV (zstd-compressed),
     filter to rating >= 2000 & NbPlays >= 1000, and save the first
     5 000 qualifying puzzles locally.
  2. Use today's date as a PRNG seed to deterministically select 10
     puzzles from the bank.
  3. Write the selection to output/daily_puzzles.json.
"""

import csv
import hashlib
import io
import json
import logging
import random
import sys
from datetime import date
from pathlib import Path

import requests
import zstandard as zstd

from scraper_utils import polite_session

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
PUZZLE_BANK = OUTPUT_DIR / "puzzle_bank.csv"
DAILY_JSON = OUTPUT_DIR / "daily_puzzles.json"

LICHESS_DB_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"

MIN_RATING = 2000
MIN_PLAYS = 1000
BANK_TARGET = 5000   # how many puzzles to cache locally
DAILY_COUNT = 10     # puzzles per day

# CSV columns in the Lichess puzzle database
# PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags
DB_COLUMNS = [
    "PuzzleId", "FEN", "Moves", "Rating", "RatingDeviation",
    "Popularity", "NbPlays", "Themes", "GameUrl", "OpeningTags",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Step 1 — Build / refresh the local puzzle bank
# ---------------------------------------------------------------------------

def _bank_is_valid() -> bool:
    """Return True if puzzle_bank.csv exists with enough rows."""
    if not PUZZLE_BANK.exists():
        return False
    with open(PUZZLE_BANK, newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # skip header
        count = sum(1 for _ in reader)
    if count < BANK_TARGET:
        log.info("Puzzle bank has %d rows (need %d). Will rebuild.", count, BANK_TARGET)
        return False
    return True


def build_puzzle_bank() -> None:
    """Stream the Lichess puzzle DB, filter, and write a local CSV."""
    log.info("Downloading Lichess puzzle database (streaming) …")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    session = polite_session()

    try:
        resp = session.get(LICHESS_DB_URL, stream=True, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as exc:
        # If we already have a puzzle bank on disk, keep using it
        if PUZZLE_BANK.exists():
            log.warning(
                "Lichess download failed (%s) — reusing existing puzzle bank at %s",
                exc, PUZZLE_BANK,
            )
            return
        raise

    # Set up zstd streaming decompressor
    dctx = zstd.ZstdDecompressor()
    # Wrap the raw socket iterator in a stream reader
    stream_reader = dctx.stream_reader(resp.raw)
    text_stream = io.TextIOWrapper(stream_reader, encoding="utf-8")

    kept = 0
    scanned = 0

    with open(PUZZLE_BANK, "w", newline="") as out_fh:
        writer = csv.writer(out_fh)
        writer.writerow(["PuzzleId", "FEN", "Moves", "Rating", "Themes", "GameUrl"])

        for line in text_stream:
            line = line.strip()
            if not line:
                continue
            # Skip the header row if present
            if line.startswith("PuzzleId"):
                continue

            scanned += 1
            parts = line.split(",")
            if len(parts) < 9:
                continue

            puzzle_id = parts[0]
            fen = parts[1]
            moves = parts[2]
            try:
                rating = int(parts[3])
                nb_plays = int(parts[6])
            except (ValueError, IndexError):
                continue

            if rating < MIN_RATING or nb_plays < MIN_PLAYS:
                continue

            themes = parts[7] if len(parts) > 7 else ""
            game_url = parts[8] if len(parts) > 8 else ""

            writer.writerow([puzzle_id, fen, moves, rating, themes, game_url])
            kept += 1

            if kept % 500 == 0:
                log.info("  … kept %d / scanned %d", kept, scanned)

            if kept >= BANK_TARGET:
                break

    log.info(
        "Puzzle bank built: %d puzzles kept out of %d scanned → %s",
        kept, scanned, PUZZLE_BANK,
    )
    if kept < BANK_TARGET:
        log.warning(
            "Only found %d qualifying puzzles (target was %d). "
            "The bank will still work but daily variety is reduced.",
            kept, BANK_TARGET,
        )


# ---------------------------------------------------------------------------
# Step 2 — Select today's 10 puzzles
# ---------------------------------------------------------------------------

def load_bank() -> list[dict]:
    """Read puzzle_bank.csv into a list of dicts."""
    puzzles = []
    with open(PUZZLE_BANK, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            puzzles.append(row)
    return puzzles


def select_daily(puzzles: list[dict], target_date: date) -> list[dict]:
    """Deterministically pick DAILY_COUNT puzzles for the given date."""
    seed = hashlib.sha256(target_date.isoformat().encode()).hexdigest()
    rng = random.Random(seed)
    if len(puzzles) <= DAILY_COUNT:
        return puzzles
    return rng.sample(puzzles, DAILY_COUNT)


# ---------------------------------------------------------------------------
# Step 3 — Write daily JSON
# ---------------------------------------------------------------------------

def write_daily_json(selected: list[dict], target_date: date) -> None:
    """Format and save daily_puzzles.json."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    out = {
        "date": target_date.isoformat(),
        "puzzles": [],
    }
    for p in selected:
        themes_raw = p.get("Themes", "")
        themes_list = [t.strip() for t in themes_raw.split() if t.strip()]

        game_url = p.get("GameUrl", "")
        puzzle_url = f"https://lichess.org/training/{p['PuzzleId']}"

        out["puzzles"].append({
            "id": p["PuzzleId"],
            "fen": p["FEN"],
            "moves": p["Moves"],
            "rating": int(p["Rating"]),
            "themes": themes_list,
            "url": puzzle_url,
            "game_url": game_url,
        })

    with open(DAILY_JSON, "w") as fh:
        json.dump(out, fh, indent=2)
    log.info("Wrote %d puzzles for %s → %s", len(out["puzzles"]), target_date, DAILY_JSON)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    today = date.today()
    log.info("Selecting %d difficult puzzles for %s", DAILY_COUNT, today)

    if not _bank_is_valid():
        build_puzzle_bank()

    puzzles = load_bank()
    if not puzzles:
        log.error("Puzzle bank is empty. Cannot continue.")
        sys.exit(1)

    selected = select_daily(puzzles, today)
    write_daily_json(selected, today)


if __name__ == "__main__":
    main()
