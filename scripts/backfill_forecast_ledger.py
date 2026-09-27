"""Rebuild the forecasts the site published before the forecast ledger
existed, from the committed history of output/website_data.json.

Run once, locally, from a full clone (the nightly checkout is shallow):

    .venv/bin/python scripts/backfill_forecast_ledger.py --out output/forecast_ledger_backfill.csv

Every first-parent commit that touched output/website_data.json is one
published run. Its live cards become ledger rows (pipeline/ledger.py) with
origin 'backfill', the commit as code_commit, and model_hash computed over
the model sources in that commit's own tree, so the eras line up with the
hash the nightly stamps from the files on disk.

update_log.csv is not used: it carries no start date or year for most of its
history, so its rows cannot be tied to an edition with certainty, and every
run it records also committed website_data.json.
"""
import argparse
import csv
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.ledger import LEDGER_FIELDS, ledger_rows  # noqa: E402
from shared.model_version import hash_sources, is_model_source  # noqa: E402
from shared.paths import PROJECT_DIR  # noqa: E402

WEBSITE_PATH = "output/website_data.json"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True).stdout


def published_runs(repo, ref):
    """(sha, commit ISO time) for each first-parent commit that changed the
    website payload, oldest first."""
    out = _git(repo, "log", "--first-parent", "--reverse", "--format=%H %cI", ref, "--", WEBSITE_PATH)
    return [tuple(line.split(" ", 1)) for line in out.decode().splitlines() if line.strip()]


def _read_blobs(repo, blob_ids):
    """Blob bytes by id, through one `git cat-file --batch` process."""
    if not blob_ids:
        return {}
    request = "".join(f"{b}\n" for b in blob_ids).encode()
    raw = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], input=request,
                         check=True, capture_output=True).stdout
    blobs, pos = {}, 0
    for blob_id in blob_ids:
        header_end = raw.index(b"\n", pos)
        size = int(raw[pos:header_end].split()[2])
        start = header_end + 1
        blobs[blob_id] = raw[start:start + size]
        pos = start + size + 1
    return blobs


def tree_model_hash(repo, sha, cache):
    """model_hash as it would have been computed from this commit's files."""
    listing = _git(repo, "ls-tree", "-r", sha).decode().splitlines()
    sources = []
    for line in listing:
        meta, path = line.split("\t", 1)
        if meta.split()[1] == "blob" and is_model_source(path):
            sources.append((path, meta.split()[2]))
    missing = [b for _, b in sources if b not in cache]
    cache.update(_read_blobs(repo, missing))
    return hash_sources((path, cache[blob]) for path, blob in sources)


def backfill_rows(repo, ref):
    """Ledger rows for every published run reachable from ref."""
    cache, rows = {}, []
    for sha, committed in published_runs(repo, ref):
        website = json.loads(_git(repo, "show", f"{sha}:{WEBSITE_PATH}"))
        run_ts = website.get("last_updated") or committed.replace("T", " ")[:19]
        rows.extend(ledger_rows(website, run_ts=run_ts,
                                model_label=website.get("model") or "unknown",
                                model_hash=tree_model_hash(repo, sha, cache),
                                code_commit=sha[:12], origin="backfill"))
    return rows


def write_rows(rows, path):
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=LEDGER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=PROJECT_DIR)
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows = backfill_rows(args.repo, args.ref)
    write_rows(rows, args.out)
    runs = len({(r["as_of_date"], r["run_ts"]) for r in rows})
    eras = len({r["model_hash"] for r in rows})
    print(f"{len(rows)} forecasts from {runs} runs across {eras} model versions -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
