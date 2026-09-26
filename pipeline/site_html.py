"""Data-file splicing (auto_update.step_update_html).

The browser reads three generated files under docs/data/, split by when the
page needs them:

  tournaments.js       TOURNAMENT_DATA, PERFORMANCE_SUMMARY, PUZZLE_DATA;
                       loaded with the page.
  performance_data.js  PERFORMANCE_DATA; fetched when the Performance tab opens.
  chess_history.js     CHESS_HISTORY; fetched when the Puzzles tab opens.

Until 2026-09 all four consts lived in one 2.4 MB site_data.js, 55% of it
pretty-print whitespace and a third of it read only by two secondary tabs.
Payloads are compacted here, at the docs/ boundary; the output/*.json files
stay pretty so the nightly diffs remain reviewable. CHESS_HISTORY is spliced
verbatim because tests/test_chess_history.py pins the generator's bytes.

_splice_const is the single brace-scanning implementation the four consts
used to have copies of (P5). tests/test_site_data_build.py pins the behavior.
"""
import json
import os
import re as _re

from pipeline import config, stamping

# Generated file -> the consts spliced into it, in order. TOURNAMENT_DATA is
# required; every other splice is guarded on its source existing, because
# step_update_html also runs on the degraded path, where the generators have
# not run and last-known-good content must survive untouched.
DATA_FILES = {
    "tournaments.js": ("TOURNAMENT_DATA", "PERFORMANCE_SUMMARY", "PUZZLE_DATA"),
    "performance_data.js": ("PERFORMANCE_DATA",),
    "chess_history.js": ("CHESS_HISTORY",),
}


def _splice_const(text, name, payload, required=False):
    """Replace the `const <name> = {...};` block in text with payload.

    Brace-counting scan, identical to the original per-const loops: the
    block ends at the matching close brace, plus the trailing semicolon
    when present. Returns (new_text, replaced). required=True raises with
    step_update_html's original error messages instead of returning
    replaced=False.
    """
    marker = f'const {name} = '
    start = text.find(marker)
    if start == -1:
        if required:
            raise RuntimeError(f"Could not find '{marker}' in the data file")
        return text, False
    data_start = start + len(marker)
    depth = 0
    end = None
    for i in range(data_start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                # Include the semicolon after the closing brace
                end = i + 1
                if end < len(text) and text[end] == ';':
                    end += 1
                break
    if end is None:
        if required:
            raise RuntimeError(
                f"Could not find end of {name} block in the data file")
        return text, False
    return text[:start] + f'{marker}{payload};' + text[end:], True


def _compact(json_text):
    """Re-serialise without whitespace: the browser gets the same object at
    40% of the bytes, and output/*.json stay pretty for reviewable diffs."""
    return json.dumps(json.loads(json_text), separators=(",", ":"))


def _without_tournaments(obj):
    """Drop every `tournaments` key at any depth."""
    if isinstance(obj, dict):
        return {k: _without_tournaments(v) for k, v in obj.items()
                if k != "tournaments"}
    if isinstance(obj, list):
        return [_without_tournaments(v) for v in obj]
    return obj


def _performance_summary(json_text):
    """PERFORMANCE_DATA minus the per-tournament records (400 KB -> 18 KB).

    The hero tooltip, the accuracy strip and the About tab read only the
    aggregates, grades and counts; the per-tournament tables belong to the
    Performance tab, which fetches the full file when it opens.
    """
    return json.dumps(_without_tournaments(json.loads(json_text)),
                      separators=(",", ":"))


def _read(path):
    with open(path) as f:
        return f.read().strip()


def _data_path(name):
    """Derived from config.SITE_DIR at call time, so a redirected SITE_DIR
    redirects every write (tests/test_site_data_build.py)."""
    return os.path.join(config.SITE_DIR, "data", name)


def _payloads(json_data):
    """const name -> payload text, for every source that exists."""
    payloads = {"TOURNAMENT_DATA": _compact(json_data)}
    puzzles = os.path.join(config.OUTPUT_DIR, "daily_puzzles.json")
    if os.path.exists(puzzles):
        payloads["PUZZLE_DATA"] = _compact(_read(puzzles))
    performance = os.path.join(config.OUTPUT_DIR, "performance_data.json")
    if os.path.exists(performance):
        text = _read(performance)
        payloads["PERFORMANCE_DATA"] = _compact(text)
        payloads["PERFORMANCE_SUMMARY"] = _performance_summary(text)
    # CHESS_HISTORY, v3 O5 (audit/AUDIT_2026-07-25.md): this splice was
    # guarded on a file no script in the repo wrote, so it had never fired.
    # step_chess_history now renders output/chess_history.json from the
    # tracked content/chess_history.json, so the guard describes a real
    # input. Spliced verbatim: tests/test_chess_history.py pins the bytes.
    history = os.path.join(config.OUTPUT_DIR, "chess_history.json")
    if os.path.exists(history):
        payloads["CHESS_HISTORY"] = _read(history)
    return payloads


def _splice_file(name, consts, payloads):
    path = _data_path(name)
    with open(path) as f:
        text = f.read()
    original = text
    for const in consts:
        if const not in payloads:
            continue
        text, replaced = _splice_const(text, const, payloads[const],
                                       required=(const == "TOURNAMENT_DATA"))
        if replaced:
            print(f"  Updated {const} in {name}")
    if text != original:
        with open(path, "w") as f:
            f.write(text)


def _verify_tournaments(json_data):
    """Re-read tournaments.js and confirm the embedded data matches source."""
    start_marker = 'const TOURNAMENT_DATA = '
    with open(_data_path("tournaments.js")) as f:
        verify_html = f.read()
    verify_idx = verify_html.find(start_marker)
    if verify_idx == -1:
        raise RuntimeError("Post-write verification failed: TOURNAMENT_DATA "
                           "marker missing from written tournaments.js")
    source_data = json.loads(json_data)
    source_gen = source_data.get('generated', '')
    source_count = len(source_data.get('tournaments', []))
    # Extract embedded generated date for quick sanity check
    gen_match = _re.search(r'"generated"\s*:\s*"([^"]+)"',
                           verify_html[verify_idx:verify_idx + 500])
    if gen_match and gen_match.group(1) != source_gen:
        raise RuntimeError(
            f"STALE DATA DETECTED: embedded generated={gen_match.group(1)} "
            f"but source={source_gen}. tournaments.js was not updated correctly.")
    print(f"  Verified: embedded data matches source "
          f"(generated={source_gen}, {source_count} tournaments)")


def step_update_html():
    """Splice the data consts into the generated docs/data/*.js files."""
    if not os.path.exists(config.WEBSITE_JSON):
        raise RuntimeError(f"Missing {config.WEBSITE_JSON}")
    for name in DATA_FILES:
        if not os.path.exists(_data_path(name)):
            raise RuntimeError(f"Missing {_data_path(name)}")

    json_data = _read(config.WEBSITE_JSON)
    payloads = _payloads(json_data)
    for name, consts in DATA_FILES.items():
        _splice_file(name, consts, payloads)
    print(f"  Updated TOURNAMENT_DATA in {_data_path('tournaments.js')}")

    # v3 S1: publish the raw JSON where Pages actually serves it, for the Ask
    # Worker, which cannot parse a JS const. Derived from SITE_DIR at call
    # time (see _data_path): a module constant frozen at import is how a test
    # once overwrote the published endpoint with its two-tournament stub.
    site_data_json = _data_path("website_data.json")
    with open(site_data_json, 'w') as f:
        f.write(payloads["TOURNAMENT_DATA"])
    print(f"  Wrote {site_data_json} (Ask Worker data endpoint)")

    # Every data file's `?v=` is its content hash, exactly like the scripts':
    # a rebuild is a new URL, so a cache cannot outlive its contents.
    stamping._stamp_script_versions()

    _verify_tournaments(json_data)
    # G9: no docs/website_data.json copy; output/website_data.json remains
    # the source of truth.
