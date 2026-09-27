"""Which code made a forecast: a label bumped by hand when the method changes,
and a hash of every source file a published forecast passes through.

The forecast ledger (pipeline/ledger.py) stamps both on each row so the live
record can be split by model era. The hash is computed from the files, not
from git: the nightly checkout is shallow, and a local run has no commit for
uncommitted edits.
"""
import hashlib
import os
from pathlib import Path

from shared.paths import PROJECT_DIR

MODEL_LABEL = "n5v4"

# Everything between the scraped count and the published card: the engine,
# the card builder that routes between estimators, and the helpers both use.
MODEL_SOURCES = (
    "model/*.py",
    "sitebuild/*.py",
    "shared/*.py",
    "ratio_model.py",
    "prediction_window.py",
    "feature_engineering.py",
    "pipeline_utils.py",
    "tournament_aliases.py",
)


def model_hash(root=PROJECT_DIR, patterns=MODEL_SOURCES):
    """First 16 hex digits of sha256 over the sorted source paths and bytes."""
    root = Path(root)
    files = sorted({p for pat in patterns for p in root.glob(pat) if p.is_file()})
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def code_commit(env=None):
    """The commit a CI run checked out (GITHUB_SHA), or '' outside CI."""
    env = os.environ if env is None else env
    return (env.get("GITHUB_SHA") or "")[:12]
