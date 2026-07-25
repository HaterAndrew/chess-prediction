#!/usr/bin/env python3
"""Generate output/chess_history.json from the tracked source, with validation.

v3 O5 (audit/AUDIT_2026-07-25.md). `step_update_html` has always contained a
splice for CHESS_HISTORY guarded by `if os.path.exists(output/chess_history.json)`,
and nothing in the repo ever wrote that file — so the splice had never fired and
the 146KB const inside the generated docs/data/site_data.js was hand-authored in
place. A 146KB blob living only inside a 2.2MB generated artifact has no source
of truth: any regression in the splicer silently eats it, and there is nowhere
to review a change to it.

This makes it a real pipeline input. content/chess_history.json is the tracked
source, this script validates and emits it, and the existing splice now fires.

The emitted formatting deliberately reproduces what was already embedded — one
line per entry, two-space indent — so wiring this up produces a zero-byte diff
in site_data.js. That is the proof the extraction was lossless, and it keeps
future diffs to the lines that actually changed instead of reflowing 146KB.

Usage:
    python3 scripts/gen_chess_history.py            # write output/chess_history.json
    python3 scripts/gen_chess_history.py --check    # validate only, write nothing
"""
import argparse
import calendar
import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(PROJECT_DIR, "content", "chess_history.json")
OUTPUT = os.path.join(PROJECT_DIR, "output", "chess_history.json")

CATEGORIES = {
    "world_championship", "tournament", "birth", "death",
    "milestone", "match", "record",
}
# Nothing before the first recorded modern tournament, nothing in the future.
MIN_YEAR = 1500
MAX_YEAR = 2100


class HistoryError(ValueError):
    """Raised on a malformed source file. Callers should not swallow this."""


def _valid_day_keys():
    keys = set()
    for month in range(1, 13):
        # 2020 is a leap year, so 02-29 is included.
        for day in range(1, calendar.monthrange(2020, month)[1] + 1):
            keys.add(f"{month:02d}-{day:02d}")
    return keys


def validate(data):
    """Raise HistoryError on anything that would render wrong in the browser.

    The front end looks up today's MM-DD and prints each entry verbatim, so a
    bad key is an invisible blank panel and a bad year prints as-is. Both are
    cheap to catch here and awkward to notice in production.
    """
    if not isinstance(data, dict):
        raise HistoryError(f"top level must be an object, got {type(data).__name__}")

    allowed = _valid_day_keys()
    bad_keys = sorted(set(data) - allowed)
    if bad_keys:
        raise HistoryError(f"not MM-DD calendar dates: {bad_keys[:5]}")

    for key, entries in sorted(data.items()):
        if not isinstance(entries, list) or not entries:
            raise HistoryError(f"{key}: expected a non-empty list of entries")
        for n, entry in enumerate(entries):
            where = f"{key}[{n}]"
            if not isinstance(entry, dict):
                raise HistoryError(f"{where}: expected an object")
            missing = {"year", "event", "category"} - set(entry)
            if missing:
                raise HistoryError(f"{where}: missing {sorted(missing)}")
            extra = set(entry) - {"year", "event", "category"}
            if extra:
                raise HistoryError(f"{where}: unexpected keys {sorted(extra)}")
            if not isinstance(entry["year"], int):
                raise HistoryError(f"{where}: year must be an int, got {entry['year']!r}")
            if not MIN_YEAR <= entry["year"] <= MAX_YEAR:
                raise HistoryError(f"{where}: year {entry['year']} outside {MIN_YEAR}-{MAX_YEAR}")
            if not isinstance(entry["event"], str) or not entry["event"].strip():
                raise HistoryError(f"{where}: event must be a non-empty string")
            if entry["category"] not in CATEGORIES:
                raise HistoryError(
                    f"{where}: category {entry['category']!r} not in {sorted(CATEGORIES)}")
    return data


def serialize(data):
    """Render in the shape already embedded in site_data.js: one entry per line.

    json.dumps(indent=2) would explode every entry across four lines and reflow
    the whole 146KB on first write. Matching the existing shape means wiring
    the generator in changes nothing, which is what makes the change reviewable.
    """
    lines = ["{"]
    keys = sorted(data)
    for i, key in enumerate(keys):
        lines.append(f'  {json.dumps(key)}: [')
        entries = data[key]
        for n, entry in enumerate(entries):
            # Key order is fixed rather than dict-insertion order so a
            # hand-edited source cannot reorder fields in the output.
            body = ", ".join(
                f'{json.dumps(k)}: {json.dumps(entry[k], ensure_ascii=False)}'
                for k in ("year", "event", "category"))
            comma = "," if n < len(entries) - 1 else ""
            lines.append(f'    {{{body}}}{comma}')
        lines.append("  ]" + ("," if i < len(keys) - 1 else ""))
    lines.append("}")
    return "\n".join(lines)


def build(check_only=False):
    if not os.path.exists(SOURCE):
        raise HistoryError(
            f"missing source {SOURCE}. This file is hand-authored and tracked; "
            "it is the only source for CHESS_HISTORY.")
    with open(SOURCE) as f:
        data = json.load(f)
    validate(data)
    rendered = serialize(data)

    days = len(data)
    entries = sum(len(v) for v in data.values())
    if check_only:
        print(f"chess_history source valid: {days} days, {entries} entries")
        return rendered

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    tmp = OUTPUT + ".tmp"
    with open(tmp, "w") as f:
        f.write(rendered)
    os.replace(tmp, OUTPUT)
    print(f"  Wrote {OUTPUT} ({days} days, {entries} entries)")
    return rendered


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="validate the source and write nothing")
    args = ap.parse_args()
    try:
        build(check_only=args.check)
    except HistoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
