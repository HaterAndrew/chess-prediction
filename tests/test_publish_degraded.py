"""The nightly's failure step publishes a stale banner over the last published
data. It used to publish only when auto_update.py had stamped
pipeline_degraded itself, so a red test gate after a good predict step (or a
crash before the stamp) exited quietly: the site kept serving day-old numbers
with no banner while the pipeline issue sat open."""
import json
import os
import subprocess

import pytest

from pipeline import publish_degraded as pd_mod

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TONIGHT = "2026-10-04 01:40:00"


def test_this_runs_own_stamp_is_kept():
    website = {"is_stale": True, "pipeline_degraded": True,
               "degraded_reason": "data-health CRITICAL", "degraded_at": "2026-10-04 01:30:00"}
    assert pd_mod.failure_flags(website, {}, "test + lint gate", TONIGHT) == website


def test_an_unstamped_failure_still_gets_a_banner():
    flags = pd_mod.failure_flags({"is_stale": False}, {}, "test + lint gate", TONIGHT)
    assert flags["is_stale"] is True and flags["pipeline_degraded"] is True
    assert "test + lint gate" in flags["degraded_reason"]
    assert flags["degraded_at"] == TONIGHT


def test_last_nights_stamp_is_not_reported_as_tonights():
    """A run that dies before auto_update stamps leaves the published file,
    with last night's reason, in the working tree."""
    old = {"pipeline_degraded": True, "degraded_reason": "old", "degraded_at": "2026-10-03 01:30:00"}
    flags = pd_mod.failure_flags(old, old, "prediction step", TONIGHT)
    assert "prediction step" in flags["degraded_reason"] and flags["degraded_at"] == TONIGHT


def _published_repo(tmp_path, payload=None):
    """A repo whose last commit is the published data."""
    repo = tmp_path / "repo"
    (repo / "output").mkdir(parents=True)
    (repo / "docs").mkdir()
    wd = repo / "output" / "website_data.json"
    wd.write_text(json.dumps(payload or {"tournaments": ["published"], "is_stale": False}))
    (repo / "docs" / "keep.txt").write_text("x")
    for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "published"]):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       check=True, capture_output=True)
    return repo, wd


def test_publish_restores_last_published_data_and_applies_the_flags(tmp_path):
    repo, wd = _published_repo(tmp_path)
    # The failed run left fresh, untested output behind.
    wd.write_text(json.dumps({"tournaments": ["untested"], "is_stale": False}))
    pd_mod.publish(str(repo), "test + lint gate", TONIGHT)

    data = json.loads(wd.read_text())
    assert data["tournaments"] == ["published"]
    assert data["pipeline_degraded"] is True and data["is_stale"] is True
    assert "test + lint gate" in data["degraded_reason"]


def test_a_half_written_payload_still_publishes_the_banner(tmp_path):
    """The old step exited when the file would not parse, which is exactly
    when a crash mid-write leaves it."""
    repo, wd = _published_repo(tmp_path)
    wd.write_text('{"tournaments": [')
    pd_mod.publish(str(repo), "prediction step", TONIGHT)

    data = json.loads(wd.read_text())
    assert data["tournaments"] == ["published"]
    assert data["pipeline_degraded"] is True


def test_a_failed_restore_stamps_nothing(tmp_path):
    repo, wd = _published_repo(tmp_path)
    wd.write_text(json.dumps({"tournaments": ["untested"]}))
    with pytest.raises(RuntimeError, match="could not restore"):
        pd_mod.publish(str(repo), "test + lint gate", TONIGHT, ref="no-such-ref")
    assert json.loads(wd.read_text()) == {"tournaments": ["untested"]}


def test_a_published_file_without_tournaments_is_not_stamped(tmp_path):
    repo, wd = _published_repo(tmp_path, payload={"is_stale": False})
    with pytest.raises(RuntimeError, match="no tournaments"):
        pd_mod.publish(str(repo), "test + lint gate", TONIGHT)


def test_the_workflow_restores_from_the_remote_and_names_the_failed_step():
    path = os.path.join(PROJECT_ROOT, ".github", "workflows", "daily_update.yml")
    with open(path) as fh:
        yml = fh.read()
    banner = yml.split("Publish degraded-state banner on failure")[1].split("Pipeline summary")[0]
    assert 'python3 -m pipeline.publish_degraded "$FAILED_STEP" FETCH_HEAD' in banner
    assert banner.index("git fetch") < banner.index("pipeline.publish_degraded")
    assert "steps.gate.outcome == 'failure'" in banner
    assert 'if not degraded.get("pipeline_degraded")' not in banner
