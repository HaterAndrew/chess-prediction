"""Publish the stale banner after a failed nightly run (daily_update.yml).

v3 O1: on a failure the commit step does not run, so the site would keep
serving day-old numbers as current. This puts back the last published
output/ and docs/ (a run that died partway may have left half-written model
files) and applies the degraded flags to it. Last-known-good data behind an
honest banner beats fresh-looking garbage.

The flags come from auto_update.py when it failed itself this run. Any other
failure (a red test gate after a good predict, a crash before the stamp)
used to exit here without a banner; it now gets a stamp naming the failed
step.

Usage: python -m pipeline.publish_degraded "<failed step>" [<published ref>]
The ref defaults to HEAD; the workflow passes the fetched remote branch, since
a failed push leaves HEAD on an unpublished local commit.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

FLAG_KEYS = ("is_stale", "pipeline_degraded", "degraded_reason", "degraded_at")
WEBSITE_JSON = os.path.join("output", "website_data.json")


def failure_flags(website, published, failed_step, now):
    """The flags to publish: auto_update's stamp when it made one this run,
    else a stamp naming the workflow step that failed. A stamp the published
    data already carries is last night's, not this run's."""
    stamped = website.get("pipeline_degraded") and website.get("degraded_at") != published.get("degraded_at")
    if stamped:
        return {k: website.get(k) for k in FLAG_KEYS}
    return {
        "is_stale": True,
        "pipeline_degraded": True,
        "degraded_reason": f"Nightly run failed at the {failed_step}; "
                           f"showing the last published data",
        "degraded_at": now,
    }


def _read(path):
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"  {path} unreadable after the failed run ({e}); stamping from the step name")
        return {}
    return data if isinstance(data, dict) else {}


def publish(repo_dir, failed_step, now, ref="HEAD"):
    """Restore output/ and docs/ from the published ref and stamp them.
    Raises rather than stamping files it could not restore."""
    path = os.path.join(repo_dir, WEBSITE_JSON)
    website = _read(path)
    restore = subprocess.run(["git", "-C", repo_dir, "checkout", ref, "--", "output/", "docs/"],
                             capture_output=True, text=True)
    if restore.returncode != 0:
        raise RuntimeError(f"could not restore the published output from {ref}: {restore.stderr.strip()}")
    published = _read(path)
    if "tournaments" not in published:
        raise RuntimeError(f"the published {WEBSITE_JSON} at {ref} has no tournaments; refusing to stamp it")
    flags = failure_flags(website, published, failed_step, now)
    with open(path, "w") as fh:
        json.dump({**published, **flags}, fh, indent=2)
    print(f"  Restored the data published at {ref} and applied degraded flags: {flags['degraded_reason']}")


def main(argv):
    failed_step = argv[1] if len(argv) > 1 and argv[1] else "workflow step"
    ref = argv[2] if len(argv) > 2 and argv[2] else "HEAD"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    publish(".", failed_step, now, ref)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
