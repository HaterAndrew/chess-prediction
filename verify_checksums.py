"""
SHA-256 checksum manifest for output CSV files.

Usage:
    python verify_checksums.py generate   # scan output/*.csv, write checksums.json
    python verify_checksums.py verify     # recompute hashes, report mismatches
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
MANIFEST_PATH = os.path.join(OUTPUT_DIR, "checksums.json")


def compute_checksum(filepath):
    """Return SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _row_count(filepath):
    """Count data rows in a CSV (excludes header)."""
    with open(filepath, "r") as f:
        lines = f.readlines()
    # Subtract 1 for header; clamp to 0 if file is empty
    return max(len(lines) - 1, 0)


def generate_manifest(output_dir=OUTPUT_DIR):
    """Scan output/*.csv, compute checksums, write checksums.json."""
    entries = []
    for name in sorted(os.listdir(output_dir)):
        if not name.endswith(".csv"):
            continue
        path = os.path.join(output_dir, name)
        entries.append({
            "filename": name,
            "sha256": compute_checksum(path),
            "row_count": _row_count(path),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    manifest = {"files": entries}
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"  Checksum manifest: {len(entries)} CSV files -> {MANIFEST_PATH}")
    return manifest


def verify_manifest(output_dir=OUTPUT_DIR):
    """Read checksums.json, recompute hashes, report mismatches."""
    if not os.path.exists(MANIFEST_PATH):
        print("ERROR: checksums.json not found. Run 'generate' first.")
        return False

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    ok = True
    for entry in manifest["files"]:
        path = os.path.join(output_dir, entry["filename"])
        if not os.path.exists(path):
            print(f"  MISSING: {entry['filename']}")
            ok = False
            continue
        actual = compute_checksum(path)
        if actual != entry["sha256"]:
            print(f"  MISMATCH: {entry['filename']}  expected={entry['sha256'][:16]}...  actual={actual[:16]}...")
            ok = False
        else:
            print(f"  OK: {entry['filename']}")

    if ok:
        print(f"\n  All {len(manifest['files'])} files verified.")
    else:
        print("\n  VERIFICATION FAILED — one or more files changed or missing.")
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("generate", "verify"):
        print("Usage: python verify_checksums.py [generate|verify]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "generate":
        generate_manifest()
    elif cmd == "verify":
        success = verify_manifest()
        sys.exit(0 if success else 1)
