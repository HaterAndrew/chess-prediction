"""Attach non-financial observation metadata after the frozen model has run."""
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
import os
import re

from shared.editions import split_edition_name
from tournament_aliases import cca_family, canonicalize_family


class EmptyObservationError(ValueError):
    """An invalid or unreadable supplemental cache cannot authorize a cohort."""


def _empty_observations(path, now):
    if path is None or not os.path.exists(path):
        return {}
    try:
        with open(path) as stream:
            raw = stream.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError()
        body = json.loads(raw)
        if not isinstance(body, dict) or set(body) != {"version", "records"} or type(body["version"]) is not int or body["version"] != 1:
            raise ValueError()
        if not isinstance(body["records"], list) or len(body["records"]) > 2000:
            raise ValueError()
        verified = {}
        seen = set()
        for row in body["records"]:
            if (not isinstance(row, dict) or set(row) != {"family", "year", "source_as_of", "total"}
                    or not isinstance(row["family"], str) or not 0 < len(row["family"]) <= 200
                    or type(row["year"]) is not int or not 2020 <= row["year"] <= 2035
                    or type(row["total"]) is not int or row["total"] != 0):
                raise ValueError()
            source = datetime.fromisoformat(row["source_as_of"].replace("Z", "+00:00"))
            if source.tzinfo is None:
                raise ValueError()
            key = (canonicalize_family(row["family"]), row["year"])
            if key in seen:
                raise ValueError()
            seen.add(key)
            if timedelta(0) <= now - source <= timedelta(hours=36):
                verified[key] = row["source_as_of"]
        return verified
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise EmptyObservationError("Empty registration observation cache invalid") from error


def attach_receipt_observations(data, scrape_path, empty_path=None, now=None):
    now = now or datetime.now(timezone.utc)
    empty = _empty_observations(empty_path, now)
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
        source = empty.get((canonicalize_family(card['family']), card['year']))
        if card['current_count'] == 0 and source:
            card['count_observed_at'] = source
            card['count_cohort_hash'] = hashlib.sha256(b'').hexdigest()
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
        if source and card['current_count'] == 0 and timestamp <= datetime.fromisoformat(source.replace('Z', '+00:00')):
            continue
        card['count_observed_at'] = observed
        card['count_cohort_hash'] = cohort
