"""site_data.js splicing (auto_update.step_update_html).

The four data consts used to be spliced by four copy-paste brace-scan
loops; _splice_const is the single shared implementation (P5). Output is
byte-identical -- tests/test_site_data_build.py pins the behavior.
"""
import json
import os
import re as _re

from pipeline import config, stamping


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
            raise RuntimeError(f"Could not find '{marker}' in site_data.js")
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
                f"Could not find end of {name} block in site_data.js")
        return text, False
    return text[:start] + f'{marker}{payload};' + text[end:], True


def step_update_html():
    """Splice the data consts into docs/data/site_data.js (externalized L15)."""
    if not os.path.exists(config.WEBSITE_JSON):
        raise RuntimeError(f"Missing {config.WEBSITE_JSON}")
    if not os.path.exists(config.SITE_DATA_JS):
        raise RuntimeError(f"Missing {config.SITE_DATA_JS}")

    with open(config.WEBSITE_JSON, 'r') as f:
        json_data = f.read().strip()

    with open(config.SITE_DATA_JS, 'r') as f:
        html = f.read()

    new_html, _ = _splice_const(html, 'TOURNAMENT_DATA', json_data,
                                required=True)

    # Also embed the optional consts whose source files exist.
    #
    # CHESS_HISTORY, v3 O5 (audit/AUDIT_2026-07-25.md): this splice was
    # guarded on a file no script in the repo wrote, so it had never fired
    # and the const was whatever someone hand-typed into the generated
    # site_data.js. step_chess_history now renders it from the tracked
    # content/chess_history.json, so the guard below describes a real input.
    # It stays a guard rather than an assert because step_update_html is
    # also called on the degraded-pipeline path, where the generator has not
    # run and last-known-good content must survive untouched.
    for name, src in (
        ('PUZZLE_DATA', os.path.join(config.OUTPUT_DIR, "daily_puzzles.json")),
        ('CHESS_HISTORY', os.path.join(config.OUTPUT_DIR, "chess_history.json")),
        ('PERFORMANCE_DATA', os.path.join(config.OUTPUT_DIR, "performance_data.json")),
    ):
        if os.path.exists(src):
            with open(src, 'r') as f:
                payload = f.read().strip()
            new_html, replaced = _splice_const(new_html, name, payload)
            if replaced:
                print(f"  Updated {name} in site_data.js")

    with open(config.SITE_DATA_JS, 'w') as f:
        f.write(new_html)

    print(f"  Updated TOURNAMENT_DATA in {config.SITE_DATA_JS}")

    # v3 S1: publish the raw JSON where GitHub Pages actually serves it. The
    # Ask Worker's DATA_URL pointed at /chess-prediction/website_data.json, which
    # 404s — Pages serves docs/, and the data lived only inside site_data.js as a
    # JS const the Worker cannot parse. Every /ask request therefore failed at
    # 502. Writing the JSON alongside site_data.js gives the Worker a real
    # endpoint without teaching it to scrape a JavaScript file.
    # Derived here rather than read from the module constant so that redirecting
    # SITE_DIR actually redirects this write. SITE_DATA_JSON is computed at
    # import from the real SITE_DIR, so a test that monkeypatches SITE_DIR still
    # wrote here — to the published file. tests/test_site_data_build.py did
    # exactly that, and left a two-tournament stub
    # ({"generated": "2026-07-07", ... "family": "X"}) sitting in
    # docs/data/website_data.json, which is the endpoint the Ask Worker fetches.
    # The file is untracked, so it would have been committed in that state.
    # Its own fixture comment warns about this class of bug; S1 reintroduced it
    # through a constant the fixture did not know to patch.
    site_data_json = os.path.join(config.SITE_DIR, "data", "website_data.json")
    with open(site_data_json, 'w') as f:
        f.write(json_data)
    print(f"  Wrote {site_data_json} (Ask Worker data endpoint)")

    stamping._stamp_site_data_version(json_data)

    # Post-write verification: re-read and confirm embedded data matches source
    start_marker = 'const TOURNAMENT_DATA = '
    with open(config.SITE_DATA_JS, 'r') as f:
        verify_html = f.read()
    verify_idx = verify_html.find(start_marker)
    if verify_idx == -1:
        raise RuntimeError("Post-write verification failed: TOURNAMENT_DATA marker missing from written site_data.js")
    source_data = json.loads(json_data)
    source_gen = source_data.get('generated', '')
    source_count = len(source_data.get('tournaments', []))
    # Extract embedded generated date for quick sanity check
    gen_match = _re.search(r'"generated"\s*:\s*"([^"]+)"', verify_html[verify_idx:verify_idx+500])
    if gen_match:
        embedded_gen = gen_match.group(1)
        if embedded_gen != source_gen:
            raise RuntimeError(
                f"STALE DATA DETECTED: embedded generated={embedded_gen} but source={source_gen}. "
                f"The HTML was not updated correctly."
            )
    print(f"  Verified: embedded data matches source (generated={source_gen}, {source_count} tournaments)")
    # G9: the app reads docs/data/site_data.js (L15 externalization); the old
    # docs/website_data.json double-ship (a 1.4MB daily-churn copy nothing
    # fetches) is gone. output/website_data.json remains the source of truth.
