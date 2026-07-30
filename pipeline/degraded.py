"""Mid-run failure stamping (auto_update, verbatim)."""
import json
import os

from pipeline import config, warns
from pipeline.site_html import step_update_html
from pipeline.stamping import _atomic_write_json


def mark_pipeline_degraded(reason, website_json=None):
    """Stamp the published data as stale after a mid-run pipeline failure.

    v3 O1 (audit/AUDIT_2026-07-25.md). The daily run regenerates
    website_data.json early (04d) and only stamps freshness late, so a crash in
    between leaves a half-built file on disk carrying the PREVIOUS run's
    `is_stale: false`. The site then presents whatever survived as current data.

    This marks the failure honestly:
      * is_stale = True and pipeline_degraded = True, so app.js's staleness gate
        fires and the banner renders;
      * degraded_reason records what failed, for the health dashboard;
      * last_updated is NOT advanced — the data genuinely is not from this run,
        and moving the timestamp would relabel stale numbers as fresh.

    Then re-splices site_data.js so the flag actually reaches the browser (the
    page reads site_data.js, not website_data.json).

    Returns True if the flag was written. Never raises on a missing file: this
    runs from an exception handler and must not mask the original failure.
    """
    path = website_json or config.WEBSITE_JSON
    if not os.path.exists(path):
        print(f"  WARNING: {path} not found — cannot mark degraded state")
        return False

    with open(path, 'r') as f:
        data = json.load(f)

    data['is_stale'] = True
    data['pipeline_degraded'] = True
    data['degraded_reason'] = str(reason)[:300]
    data['degraded_at'] = config.RUN_TS

    _atomic_write_json(path, data)
    print(f"  Stamped DEGRADED — is_stale=True, reason={str(reason)[:120]}")

    # Push the flag through to the file the browser actually loads.
    try:
        step_update_html()
        print("  Re-spliced site_data.js with the degraded flag")
    except Exception as e:
        print(f"  WARNING: could not re-splice site_data.js: {e}")

    # Persist the warning trail even though the run is aborting.
    warns._PIPELINE_WARNINGS.append({
        'step': 'PIPELINE FAILURE',
        'text': f'Run aborted; serving last-known data behind a stale banner. Reason: {reason}',
    })
    try:
        warns.write_audit_warnings()
    except Exception as e:
        print(f"  WARNING: could not write audit warnings: {e}")
    return True
