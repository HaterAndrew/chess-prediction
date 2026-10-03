"""Pipeline warning capture (auto_update, verbatim).

_PIPELINE_WARNINGS is THE shared mutable: every producer appends via
warns._PIPELINE_WARNINGS (attribute access at call time) so a test that
rebinds it sees every downstream append.
"""
import json
import os

from pipeline import config
from pipeline.stamping import _atomic_write_json


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


ENRICHMENT_PREFIX = "Enrichment: "


def nightly_owns(step):
    """The nightly pipeline owns every step except the weekly enrichment
    scrapers, which run_enrichment.py names "Enrichment: <scraper>"."""
    return not str(step).startswith(ENRICHMENT_PREFIX)


def merge_warnings(previous, current, owns, generated):
    """Combine this run's warnings with the previous file's.

    audit_warnings.json has two writers (nightly, weekly enrichment). Entries
    for steps this run owns are replaced, including steps that ran clean;
    entries for other steps are kept with the time they were recorded.
    Without this, the weekly run erased the nightly warnings (2026-10-03).
    """
    previous = previous or {}
    kept = []
    for w in previous.get('warnings', []):
        if owns(w.get('step', '')):
            continue
        kept.append({**w, 'generated': w.get('generated', previous.get('generated'))})
    fresh = [{**w, 'generated': generated} for w in group_warnings(current)['warnings']]
    merged = fresh + kept
    return {
        'generated': generated,
        'count': len(merged),
        'total_occurrences': sum(w.get('count', 1) for w in merged),
        'warnings': merged,
    }


AUDIT_FILE_STEP = "audit_warnings.json"


def _read_previous(path):
    """The previous payload, or None when there is none. An unreadable file
    is recorded as a warning of this run: overwriting it loses whatever the
    other writer had recorded."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get('warnings', []), list):
            raise ValueError("not a warnings payload")
        return data
    except (OSError, ValueError) as e:
        text = (f"could not read the previous {os.path.basename(path)} ({e}); "
                f"warnings recorded by the other writer were lost")
        print(f"  WARNING: {text}")
        _PIPELINE_WARNINGS.append({'step': AUDIT_FILE_STEP, 'text': text})
        return None


def write_audit_warnings(owns=nightly_owns):
    """Write pipeline warnings to output/audit_warnings.json and docs/.
    AUDIT.md follow-up #2; deduped per v5 Cat V; merged with the other
    writer's entries per merge_warnings."""
    out_path = os.path.join(config.OUTPUT_DIR, "audit_warnings.json")
    previous = _read_previous(out_path)
    def replaced(step):
        return owns(step) or step == AUDIT_FILE_STEP
    payload = merge_warnings(previous, _PIPELINE_WARNINGS, replaced, config.RUN_TS)
    _atomic_write_json(out_path, payload)
    _atomic_write_json(os.path.join(config.SITE_DIR, "audit_warnings.json"), payload)
    if payload['warnings']:
        print(f"\n  Captured {payload['count']} distinct pipeline warning(s) "
              f"({payload['total_occurrences']} total) → {out_path}")
        for w in payload['warnings']:
            times = f" ×{w['count']}" if w['count'] > 1 else ""
            print(f"    [{w['step']}]{times} {w['text'][:120]}")
    else:
        print(f"\n  No pipeline warnings captured → {out_path}")
    print("  Copied audit_warnings.json to docs/")
