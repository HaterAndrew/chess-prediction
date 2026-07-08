#!/usr/bin/env python3
"""Single-source the front-end cache-busting versions (G5).

styles.css?v=N and app.js?v=N each appear in BOTH docs/index.html and
docs/sw.js, and the SW CACHE_NAME must bump whenever either changes. Hand-editing
one and forgetting the other is exactly how a deploy ships stale assets. This
tool bumps them together and can verify they agree.

    python3 scripts/bump_assets.py css        # bump styles.css?v (+ CACHE_NAME)
    python3 scripts/bump_assets.py js          # bump app.js?v    (+ CACHE_NAME)
    python3 scripts/bump_assets.py css js      # bump both
    python3 scripts/bump_assets.py --check     # fail if the two files disagree
"""
import argparse
import os
import re
import sys

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")
INDEX = os.path.join(DOCS, "index.html")
SW = os.path.join(DOCS, "sw.js")

ASSETS = {
    "css": r"styles\.css\?v=(\d+)",
    "js": r"app\.js\?v=(\d+)",
}
CACHE_RE = r"cca-predictor-v(\d+)"


def _read(path):
    with open(path) as f:
        return f.read()


def _versions(text, pattern):
    return [int(m) for m in re.findall(pattern, text)]


def check():
    """Return 0 if every asset version agrees across index.html and sw.js."""
    idx, sw = _read(INDEX), _read(SW)
    ok = True
    for name, pat in ASSETS.items():
        seen = set(_versions(idx, pat)) | set(_versions(sw, pat))
        if len(seen) > 1:
            print(f"DRIFT: {name} version differs across files: {sorted(seen)}")
            ok = False
    if ok:
        print("asset versions consistent")
    return 0 if ok else 1


def bump(which):
    idx, sw = _read(INDEX), _read(SW)
    literals = {"css": "styles.css?v=", "js": "app.js?v="}
    for name in which:
        pat = ASSETS[name]
        cur = max(_versions(idx, pat) + _versions(sw, pat), default=0)
        nxt = cur + 1
        idx = re.sub(pat, literals[name] + str(nxt), idx)
        sw = re.sub(pat, literals[name] + str(nxt), sw)
        print(f"{name}: v{cur} -> v{nxt}")
    # any asset bump invalidates the SW cache
    cache_cur = max(_versions(sw, CACHE_RE), default=0)
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
    ap.add_argument("assets", nargs="*", choices=["css", "js"], help="assets to bump")
    ap.add_argument("--check", action="store_true", help="verify versions agree; do not write")
    args = ap.parse_args(argv)
    if args.check:
        return check()
    if not args.assets:
        ap.error("name at least one asset to bump (css/js) or pass --check")
    return bump(sorted(set(args.assets)))


if __name__ == "__main__":
    sys.exit(main())
