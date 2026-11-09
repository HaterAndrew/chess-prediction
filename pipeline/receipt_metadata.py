"""Attach non-financial observation metadata after the frozen model has run."""
import csv
from datetime import datetime
import os
import re

from shared.editions import split_edition_name
from tournament_aliases import cca_family, canonicalize_family


def attach_receipt_observations(data, scrape_path):
    latest = {}
    if os.path.exists(scrape_path):
        with open(scrape_path, newline='') as stream:
            for row in csv.DictReader(stream):
                _, year = split_edition_name(row['tournament_name'])
                if year is None:
                    continue
                key = (canonicalize_family(cca_family(row['tournament_name'])), year)
                if key not in latest or row['date'] >= latest[key]['date']:
                    latest[key] = row
    for card in data.get('tournaments', []):
        card['count_observed_at'] = None
        card['count_cohort_hash'] = None
        row = latest.get((canonicalize_family(card['family']), card['year']))
        if not row or int(row['entry_count']) != card['current_count']:
            continue
        observed = row.get('count_observed_at', '') or ''
        cohort = row.get('count_cohort_hash', '') or ''
        if not re.fullmatch(r'[a-f0-9]{64}', cohort):
            continue
        try:
            timestamp = datetime.fromisoformat(observed)
        except ValueError:
            continue
        if timestamp.tzinfo is None:
            continue
        card['count_observed_at'] = observed
        card['count_cohort_hash'] = cohort
