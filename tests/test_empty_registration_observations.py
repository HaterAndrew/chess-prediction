"""Only a complete, successful native zero report proves an empty cohort."""
import copy
import hashlib
import json
from datetime import datetime, timezone

import pytest

from dataprep.registration_observations import write_empty_observations
from pipeline.receipt_metadata import attach_receipt_observations

NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)


def record():
    return dict(ok=True, family="Example Open", year=2027,
                data=dict(total=0, source_as_of="2026-11-11T11:00:00.000Z"))


def test_verified_empty_source_supplies_zero_cohort_without_creating_a_forecast(tmp_path):
    path = tmp_path / "empty_registration_observations.json"
    write_empty_observations(tmp_path, [record()], NOW)
    data = {"tournaments": [dict(family="Example Open", year=2027, current_count=0, point_estimate=None)]}
    attach_receipt_observations(data, tmp_path / "missing.csv", path, NOW)
    card = data["tournaments"][0]
    assert card["count_cohort_hash"] == hashlib.sha256(b"").hexdigest()
    assert card["count_observed_at"] == record()["data"]["source_as_of"]
    assert card["point_estimate"] is None


@pytest.mark.parametrize("change", ["failed", "nonzero", "stale", "future", "wrong_year", "different_count"])
def test_zero_proof_does_not_cross_failure_freshness_or_edition_boundaries(tmp_path, change):
    source = record()
    if change == "failed": source["ok"] = False
    if change == "nonzero": source["data"]["total"] = 1
    if change == "stale": source["data"]["source_as_of"] = "2026-11-09T11:00:00.000Z"
    if change == "future": source["data"]["source_as_of"] = "2026-11-11T13:00:00.000Z"
    write_empty_observations(tmp_path, [source], NOW)
    card = dict(family="Example Open", year=2026 if change == "wrong_year" else 2027,
                current_count=1 if change == "different_count" else 0)
    attach_receipt_observations({"tournaments": [card]}, tmp_path / "missing.csv",
                                tmp_path / "empty_registration_observations.json", NOW)
    assert card["count_cohort_hash"] is None


def test_failed_report_clears_the_previous_empty_proof(tmp_path):
    write_empty_observations(tmp_path, [record()], NOW)
    failed = copy.deepcopy(record())
    failed["ok"] = False
    write_empty_observations(tmp_path, [failed], NOW)
    assert json.loads((tmp_path / "empty_registration_observations.json").read_text())["records"] == []


def test_corrupt_cache_fails_loud_without_claiming_zero(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"version":1,"records":[{"total":0}]}')
    with pytest.raises(ValueError, match="Empty registration observation"):
        attach_receipt_observations({"tournaments": []}, tmp_path / "missing.csv", path, NOW)


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_edition_rejects_even_when_one_row_is_expired(tmp_path, reverse):
    fresh = dict(family="Example Open", year=2027, total=0, source_as_of="2026-11-11T11:00:00.000Z")
    stale = dict(fresh, source_as_of="2026-11-09T11:00:00.000Z")
    path = tmp_path / "duplicates.json"
    path.write_text(json.dumps(dict(version=1, records=[fresh, stale] if reverse else [stale, fresh])))
    with pytest.raises(ValueError, match="Empty registration observation"):
        attach_receipt_observations({"tournaments": []}, tmp_path / "missing.csv", path, NOW)


@pytest.mark.parametrize("is_stale", [False, True])
@pytest.mark.parametrize("cache_error", ["schema", "read"])
def test_corrupt_optional_cache_warns_and_preserves_independent_csv_proofs(tmp_path, monkeypatch, capsys, is_stale, cache_error):
    from pipeline import config, warns
    from pipeline.stamping import _stamp_stale_flag
    output = tmp_path / "website_data.json"
    output.write_text(json.dumps(dict(tournaments=[
        dict(family="Positive Open", year=2027, current_count=1),
        dict(family="Empty Open", year=2027, current_count=0, count_cohort_hash="old", count_observed_at="old"),
    ])))
    scrape = tmp_path / "scrape.csv"
    scrape.write_text('date,tournament_name,entry_count,count_observed_at,count_cohort_hash\n'
                      '2026-11-11,2027 Positive Open,1,2026-11-11T11:00:00+00:00,' + 'a'*64 + '\n')
    (tmp_path / "empty_registration_observations.json").write_text('{"broken":true}')
    if cache_error == "read":
        import builtins
        original_open = builtins.open
        def guarded_open(path, *args, **kwargs):
            if str(path) == str(tmp_path / "empty_registration_observations.json"):
                raise PermissionError("synthetic optional-cache read failure")
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(config, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "WEBSITE_JSON", str(output))
    monkeypatch.setattr(config, "SCRAPE_CSV", str(scrape))
    monkeypatch.setattr(warns, "_PIPELINE_WARNINGS", [])
    _stamp_stale_flag(is_stale)
    data = json.loads(output.read_text())
    assert data["is_stale"] is is_stale
    assert data["tournaments"][0]["count_cohort_hash"] == 'a'*64
    assert data["tournaments"][1]["count_cohort_hash"] is None
    assert data["tournaments"][1]["count_observed_at"] is None
    assert "WARNING: Empty registration observation cache invalid" in capsys.readouterr().out
    assert warns._PIPELINE_WARNINGS == [dict(step="Registration observations",
        text="Empty registration observation cache invalid; withheld supplemental empty proofs.")]
