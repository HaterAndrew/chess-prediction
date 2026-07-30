"""Pipeline warning capture (auto_update, verbatim).

_PIPELINE_WARNINGS is THE shared mutable: every producer appends via
warns._PIPELINE_WARNINGS (attribute access at call time) so a test that
rebinds it sees every downstream append.
"""
import json
import os

from pipeline import config


_PIPELINE_WARNINGS = []


def _harvest_warnings(step_name, stdout):
    """Pull lines starting with WARNING: out of a step's stdout into the
    pipeline-wide warning list. Exposed via output/audit_warnings.json so
    CI can surface them in the step summary instead of letting them rot
    in auto_update.log. AUDIT.md follow-up #2."""
    if not stdout:
        return
    for line in stdout.split('\n'):
        stripped = line.strip()
        # Match the audit-emitted format: "WARNING: <message>" anywhere on the line.
        if 'WARNING:' in stripped:
            # Strip leading whitespace + any leading "WARNING:" prefix from the captured text
            idx = stripped.find('WARNING:')
            text = stripped[idx + len('WARNING:'):].strip()
            _PIPELINE_WARNINGS.append({'step': step_name, 'text': text})


def group_warnings(warnings):
    """Fold identical (step, text) pairs into one entry with a count.

    v5 Cat V: the payload used to carry every duplicate verbatim — 200 of 216
    entries were the same recalibration sentence repeated per T bucket, which
    buried the one warning that mattered, bloated the service-worker-precached
    site file to 50KB, and printed 216 rows into the CI step summary nightly.
    `count` = DISTINCT warnings (the site's count===0 green pill and the step
    summary's zero-branch keep working: 0 distinct ⇔ 0 total);
    `total_occurrences` preserves the raw magnitude. First-seen order.
    """
    grouped = {}
    for w in warnings:
        key = (w['step'], w['text'])
        if key in grouped:
            grouped[key]['count'] += 1
        else:
            grouped[key] = {'step': w['step'], 'text': w['text'], 'count': 1}
    return {
        'count': len(grouped),
        'total_occurrences': len(warnings),
        'warnings': list(grouped.values()),
    }


def write_audit_warnings():
    """Write pipeline warnings to output/audit_warnings.json for CI consumption.
    AUDIT.md follow-up #2; deduped per v5 Cat V."""
    out_path = os.path.join(config.OUTPUT_DIR, "audit_warnings.json")
    payload = {'generated': config.RUN_TS, **group_warnings(_PIPELINE_WARNINGS)}
    with open(out_path, 'w') as f:
        json.dump(payload, f, indent=2)
    site_path = os.path.join(config.SITE_DIR, "audit_warnings.json")
    with open(site_path, 'w') as f:
        json.dump(payload, f, indent=2)
    if payload['warnings']:
        print(f"\n  Captured {payload['count']} distinct pipeline warning(s) "
              f"({payload['total_occurrences']} total) → {out_path}")
        for w in payload['warnings']:
            times = f" ×{w['count']}" if w['count'] > 1 else ""
            print(f"    [{w['step']}]{times} {w['text'][:120]}")
    else:
        print(f"\n  No pipeline warnings captured → {out_path}")
    print("  Copied audit_warnings.json to docs/")
