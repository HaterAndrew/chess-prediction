"""Persist empty cohorts proven by validated native registration reports."""
import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path

from dataprep.registration_contract import _time

EMPTY_OBSERVATIONS = "empty_registration_observations.json"


def write_empty_observations(output_dir, records, now):
    """Called only after validate_feed and successful corpus reconciliation."""
    empty = []
    for record in records:
        source = record.get("data")
        if not record["ok"] or not source or source["total"] != 0:
            continue
        age = now - _time(source["source_as_of"], True)
        if timedelta(0) <= age <= timedelta(hours=36):
            empty.append(dict(family=record["family"], year=record["year"],
                              source_as_of=source["source_as_of"], total=0))
    root = Path(output_dir)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=root, prefix=".empty-observations-", delete=False) as stream:
            staged = Path(stream.name)
            json.dump(dict(version=1, records=empty), stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, root / EMPTY_OBSERVATIONS)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
