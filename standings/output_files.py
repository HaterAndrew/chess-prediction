"""The output/ files the standings import and scrape read and write."""
import csv
import os

import pandas as pd

from registry.keys import summary_edition_key
from standings.importer import COLUMNS

STANDINGS_CSV = "historical_standings.csv"


def spelling_years(output_dir):
    """{family spelling: years} across the summary and the metadata."""
    summary = pd.read_csv(os.path.join(output_dir, "tournament_summary.csv"))
    meta = pd.read_csv(os.path.join(output_dir, "tournament_metadata.csv"))
    pairs = pd.concat([summary[["family", "tournament_year"]].set_axis(["family", "year"], axis=1),
                       meta[["family", "year"]]]).dropna()
    years = {}
    for family, year in zip(pairs["family"], pairs["year"]):
        years.setdefault(family, set()).add(int(year))
    return years


def final_counts(output_dir):
    """{edition key: the summary's largest final count for it}."""
    summary = pd.read_csv(os.path.join(output_dir, "tournament_summary.csv"))
    finals = {}
    for family, year, count in zip(summary["family"], summary["tournament_year"], summary["final_count"]):
        key = summary_edition_key(family, year)
        if key and pd.notna(count):
            finals[key] = max(finals.get(key, 0), int(count))
    return finals


def ended_editions(output_dir):
    """(family, year, end date) for each metadata row with an end date."""
    meta = pd.read_csv(os.path.join(output_dir, "tournament_metadata.csv"))
    meta = meta.dropna(subset=["family", "year", "end_date"])
    ends = pd.to_datetime(meta["end_date"], errors="raise").dt.date
    return list(zip(meta["family"], meta["year"].astype(int), ends))


def read_standings(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_standings(path, rows):
    rows = sorted(rows, key=lambda r: (r["tournament_name"], int(r["year"])))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
