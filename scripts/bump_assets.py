#!/usr/bin/env python3
"""Single-source the front-end cache-busting versions (G5).

Every stamped asset appears in BOTH docs/index.html and docs/sw.js, and the
SW CACHE_NAME must bump whenever any of them changes. Hand-editing one file
and forgetting the other is exactly how a deploy ships stale assets. This
tool verifies the pair agree (and can still bump a plain-counter asset).

    python3 scripts/bump_assets.py app.js      # bump one asset (+ CACHE_NAME)
    python3 scripts/bump_assets.py css js      # legacy aliases still work
    python3 scripts/bump_assets.py --check     # fail if the files disagree
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline.stamping import STAMPED_SCRIPTS

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
INDEX = os.path.join(DOCS, "index.html")
SW = os.path.join(DOCS, "sw.js")

# Patterns derive from the pipeline's stamp list (C0), so a script added to
# STAMPED_SCRIPTS is covered here automatically. Versions are content hashes
# (auto_update's _stamp_script_versions), so the pattern accepts any
# alphanumeric token: the old `(\d+)` matched the LEADING DIGITS of a hash
# and silently compared a fragment.
ASSETS = {name: rf"{re.escape(name)}\?v=([A-Za-z0-9]+)"
          for name in STAMPED_SCRIPTS}
# Legacy CLI aliases from the two-asset era.
ALIASES = {"css": "styles.css", "js": "app.js"}
CACHE_RE = r"cca-predictor-v(\d+)"


def _read(path):
    with open(path) as f:
        return f.read()


def _versions(text, pattern):
    """Version tokens as strings — they may be hashes, so do not coerce to int."""
    return re.findall(pattern, text)


def check():
    """Return 0 if every stamped asset agrees across index.html and sw.js.

    This is the guard worth keeping: whatever sets the versions, the service
    worker and the page must reference the same URL, or the SW precaches an
    asset the page never requests. An asset referenced by exactly one of the
    two files is the same failure one step earlier (the C-track's per-file
    recipe adds the script tag and the sw.js entry together), so that is
    drift too. Absent from both = not shipped yet; not this tool's business.
    """
    idx, sw = _read(INDEX), _read(SW)
    ok = True
    for name, pat in ASSETS.items():
        idx_v, sw_v = set(_versions(idx, pat)), set(_versions(sw, pat))
        if not idx_v and not sw_v:
            continue
        if not idx_v or not sw_v:
            missing = "index.html" if not idx_v else "sw.js"
            print(f"DRIFT: {name} is referenced by one file but missing from "
                  f"{missing}")
            ok = False
        elif idx_v != sw_v:
            print(f"DRIFT: {name} version differs across files: "
                  f"{sorted(idx_v | sw_v)}")
            ok = False
    if ok:
        print("asset versions consistent")
    return 0 if ok else 1


def bump(which):
    which = [ALIASES.get(name, name) for name in which]
    unknown = sorted(set(which) - set(ASSETS))
    if unknown:
        print(f"unknown asset(s): {', '.join(unknown)}")
        return 1
    idx, sw = _read(INDEX), _read(SW)

    # These versions are content hashes now, written by
    # auto_update._stamp_script_versions on every pipeline run. Incrementing a
    # hash is meaningless, and doing it by hand would be undone by the next
    # run, so say so instead of writing something that looks like it worked.
    # An asset with NO references is an error, not a silent no-op bump.
    absent = sorted(
        name for name in which
        if not _versions(idx, ASSETS[name]) + _versions(sw, ASSETS[name]))
    if absent:
        print(f"ERROR: {', '.join(absent)} not referenced by index.html or "
              f"sw.js — nothing to bump.")
        return 1
    hashed = sorted({
        name for name in which
        if any(not v.isdigit()
               for v in _versions(idx, ASSETS[name]) + _versions(sw, ASSETS[name]))
    })
    if hashed:
        print(f"REFUSING to bump {', '.join(hashed)}: the version is derived "
              f"from the file's content hash, not a counter.")
        print("Edit the asset and the next pipeline run restamps it, or run:")
        print("    python3 -c \"import auto_update as a; "
              "a._stamp_script_versions()\"")
        return 1

    for name in which:
        pat = ASSETS[name]
        cur = max((int(v) for v in _versions(idx, pat) + _versions(sw, pat)),
                  default=0)
        nxt = cur + 1
        idx = re.sub(pat, f"{name}?v={nxt}", idx)
        sw = re.sub(pat, f"{name}?v={nxt}", sw)
        print(f"{name}: v{cur} -> v{nxt}")
    # any asset bump invalidates the SW cache
    # CACHE_NAME is still a plain counter, so this one really is an int.
    cache_cur = max((int(v) for v in _versions(sw, CACHE_RE)), default=0)
    sw = re.sub(CACHE_RE, f"cca-predictor-v{cache_cur + 1}", sw)
    print(f"CACHE_NAME: v{cache_cur} -> v{cache_cur + 1}")
    with open(INDEX, "w") as f:
        f.write(idx)
    with open(SW, "w") as f:
        f.write(sw)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("assets", nargs="*",
                    choices=sorted(ASSETS) + sorted(ALIASES) + [[]],
                    help="assets to bump (filename, or legacy css/js alias)")
    ap.add_argument("--check", action="store_true",
                    help="verify versions agree; do not write")
    args = ap.parse_args(argv)
    if args.check:
        return check()
    if not args.assets:
        ap.error("name at least one asset to bump or pass --check")
    return bump(sorted(set(args.assets)))


if __name__ == "__main__":
    sys.exit(main())
