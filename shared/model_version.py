"""Which code made a forecast: a label bumped by hand when the method changes,
and a hash of every source file a published forecast passes through.

The forecast ledger (pipeline/ledger.py) stamps both on each row so the live
record can be split by model era. The hash is computed from the files, not
from git: the nightly checkout is shallow, and a local run has no commit for
uncommitted edits.
"""
import hashlib
import os
from pathlib import Path, PurePosixPath

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


def is_model_source(rel_path, patterns=MODEL_SOURCES):
    """Whether a repo-relative POSIX path is one of the model's sources: the
    pattern must match the whole path, so 'model/*.py' takes model/core.py but
    not model/sub/x.py, and 'ratio_model.py' only the root file."""
    path = PurePosixPath(rel_path)
    return any(len(path.parts) == len(PurePosixPath(p).parts) and path.match(p) for p in patterns)


def hash_sources(files):
    """First 16 hex digits of sha256 over (path, bytes) pairs in path order."""
    digest = hashlib.sha256()
    for rel_path, data in sorted(files):
        digest.update(rel_path.encode())
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def model_hash(root=PROJECT_DIR, patterns=MODEL_SOURCES):
    """hash_sources over the model's source files as they are on disk."""
    root = Path(root)
    files = {p for pat in patterns for p in root.glob(pat) if p.is_file()}
    return hash_sources((p.relative_to(root).as_posix(), p.read_bytes()) for p in files)


def code_commit(env=None):
    """The commit a CI run checked out (GITHUB_SHA), or '' outside CI."""
    env = os.environ if env is None else env
    return (env.get("GITHUB_SHA") or "")[:12]
