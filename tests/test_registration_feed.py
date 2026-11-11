"""The aggregate source must preserve existing truth/curves and stable edition IDs."""

import copy
from datetime import datetime, timezone

import pandas as pd
import pytest

from dataprep.registration_feed import FeedError, merge_feed, validate_feed

NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


def snapshot(family="Example Open", year=2026, tid="123"):
    return {
        "version": 1,
        "family": family,
        "year": year,
        "tournament_id": tid,
        "source_as_of": "2026-11-10T11:00:00.000Z",
        "active": 2,
        "withdrawn": 1,
        "total": 3,
        "ts_count": 3,
        "first_reg": "2026-02-01 14:00:00",
        "last_reg": "2026-02-02 13:00:00",
        "daily": [{"T": 0, "daily_regs": 3}],
        "calendar_daily": [
            {"date": "2026-02-01", "daily_regs": 1},
            {"date": "2026-02-02", "daily_regs": 2},
        ],
    }


def feed(*snapshots):
    return {
        "version": 1,
        "generated": "2026-11-10T12:00:00.000Z",
        "records": [
            {
                "family": s["family"],
                "year": s["year"],
                "attempted_at": s["source_as_of"],
                "ok": True,
                "reason": None,
                "data": s,
            }
            for s in snapshots
        ],
    }


def inputs(tmp_path):
    summary = pd.DataFrame(
        [
            {
                "tid": 5000,
                "tournament_name": "2026 Example Open",
                "family": "Example Open",
                "tournament_year": 2026,
                "final_count": 5,
                "has_timestamps": False,
                "ts_count": 0,
                "first_reg": None,
                "last_reg": None,
                "is_covid": False,
                "is_online": False,
                "snapshot_last_reg": None,
                "roster_pending": True,
            },
            {
                "tid": 99,
                "tournament_name": "2025 Existing Open",
                "family": "Existing Open",
                "tournament_year": 2025,
                "final_count": 2,
                "has_timestamps": True,
                "ts_count": 2,
                "first_reg": "2025-02-01 00:00:00",
                "last_reg": "2025-02-02 00:00:00",
                "is_covid": False,
                "is_online": False,
                "snapshot_last_reg": "2025-02-02 00:00:00",
                "roster_pending": False,
            },
        ]
    )
    daily = pd.DataFrame(
        [
            {"tid": 99, "T": 1, "daily_regs": 1, "cum_regs": 1, "cum_pct": 0.5},
            {"tid": 99, "T": 0, "daily_regs": 1, "cum_regs": 2, "cum_pct": 1},
        ]
    )
    summary.to_csv(tmp_path / "tournament_summary.csv", index=False)
    daily.to_csv(tmp_path / "daily_registration_counts.csv", index=False)
    pd.DataFrame(
        [
            {
                "family": "Example Open",
                "year": 2026,
                "start_date": "2026-02-02",
                "end_date": "2026-02-03",
            },
            {
                "family": "Existing Open",
                "year": 2025,
                "start_date": "2025-02-02",
                "end_date": "2025-02-03",
            },
        ]
    ).to_csv(tmp_path / "tournament_metadata.csv", index=False)
    return summary, daily


def test_empty_report_metadata_is_written_only_after_full_feed_validation(tmp_path):
    import json
    inputs(tmp_path)
    empty = snapshot()
    empty.update(active=0, withdrawn=0, total=0, ts_count=0, first_reg=None,
                 last_reg=None, daily=[], calendar_daily=[])
    assert merge_feed(tmp_path, feed(empty), NOW)["waiting"] == 1
    cache = tmp_path / "empty_registration_observations.json"
    assert json.loads(cache.read_text())["records"][0]["total"] == 0
    before = cache.read_bytes()
    invalid = copy.deepcopy(empty)
    invalid["active"] = 1
    with pytest.raises(FeedError):
        merge_feed(tmp_path, feed(invalid), NOW)
    assert cache.read_bytes() == before
    failed = feed(empty)
    failed["records"][0].update(ok=False, reason="source_timeout")
    merge_feed(tmp_path, failed, NOW)
    assert json.loads(cache.read_text())["records"] == []


def test_preserves_old_curves_scrape_peak_and_tid_and_is_idempotent(tmp_path):
    original, old_daily = inputs(tmp_path)
    result = merge_feed(tmp_path, feed(snapshot()), NOW)
    assert result["imported"] == 1
    summary = pd.read_csv(tmp_path / "tournament_summary.csv")
    row = summary.loc[summary.family == "Example Open"].iloc[0]
    assert row.tid == 5000 and row.final_count == 5 and row.ts_count == 3
    assert row.has_timestamps and not row.roster_pending
    assert row.last_reg == "2026-02-02 13:00:00"
    daily = pd.read_csv(tmp_path / "daily_registration_counts.csv")
    pd.testing.assert_frame_equal(
        daily[daily.tid == 99].reset_index(drop=True), old_daily
    )
    assert daily.loc[daily.tid == 5000, "cum_pct"].tolist() == [1.0]
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}
    assert merge_feed(tmp_path, feed(snapshot()), NOW)["imported"] == 0
    assert before == {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}


def test_existing_timestamped_manual_edition_is_not_replaced(tmp_path):
    inputs(tmp_path)
    s = snapshot("Existing Open", 2025, "99")
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}
    assert merge_feed(tmp_path, feed(s), NOW)["preserved"] == 1
    assert before == {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda x: x["records"][0]["data"].update(total=4),
        lambda x: x["records"][0]["data"].update(email="private@example.test"),
        lambda x: x["records"][0]["data"].update(first_reg="2026-02-30 00:00:00"),
        lambda x: x["records"][0]["data"]["daily"][0].update(daily_regs=2),
        lambda x: x["records"][0]["data"]["calendar_daily"][0].update(daily_regs=3),
        lambda x: x["records"][0].update(family="Another Open"),
        lambda x: x.update(generated="2027-01-01T00:00:00.000Z"),
        lambda x: x["records"].append(copy.deepcopy(x["records"][0])),
    ],
)
def test_rejects_entire_invalid_feed_before_writing(tmp_path, mutation):
    inputs(tmp_path)
    x = feed(snapshot())
    mutation(x)
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}
    with pytest.raises(FeedError):
        merge_feed(tmp_path, x, NOW)
    assert before == {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}


def test_stale_success_and_failed_last_good_are_reported_without_import(tmp_path):
    inputs(tmp_path)
    x = feed(snapshot())
    x["records"][0]["data"]["source_as_of"] = "2026-10-01T00:00:00.000Z"
    assert merge_feed(tmp_path, x, NOW)["stale"] == 1
    x = feed(snapshot())
    x["records"][0].update(ok=False, reason="source_login_expired")
    assert merge_feed(tmp_path, x, NOW)["failed"] == 1


def test_source_curves_match_original_per_registration_floor_algorithm(tmp_path):
    from dataprep.curves import build_daily_counts

    inputs(tmp_path)
    s = snapshot()
    s["first_reg"] = "2026-01-31 12:00:00"
    s["daily"] = [{"T": 2, "daily_regs": 1}, {"T": 0, "daily_regs": 2}]
    s["calendar_daily"] = [
        {"date": "2026-01-31", "daily_regs": 1},
        {"date": "2026-02-01", "daily_regs": 1},
        {"date": "2026-02-02", "daily_regs": 1},
    ]
    merge_feed(tmp_path, feed(s), NOW)
    raw = pd.DataFrame(
        {
            "tid": [5000] * 3,
            "registered_time": pd.to_datetime(
                ["2026-01-31 12:00:00", "2026-02-01 14:00:00", "2026-02-02 13:00:00"]
            ),
        }
    )
    summary = pd.DataFrame(
        {"tid": [5000], "last_reg": pd.to_datetime([s["last_reg"]]), "final_count": [5]}
    )
    expected = build_daily_counts(raw, summary, {})
    actual = pd.read_csv(tmp_path / "daily_registration_counts.csv")
    pd.testing.assert_frame_equal(
        actual[actual.tid == 5000].reset_index(drop=True),
        expected.reset_index(drop=True),
    )


def test_requires_known_unambiguous_edition_and_does_not_reassign_tid(tmp_path):
    inputs(tmp_path)
    with pytest.raises(FeedError):
        merge_feed(tmp_path, feed(snapshot("Unknown Open")), NOW)
    summary = pd.read_csv(tmp_path / "tournament_summary.csv")
    summary = pd.concat([summary, summary.iloc[:1].assign(tid=6000)])
    summary.to_csv(tmp_path / "tournament_summary.csv", index=False)
    with pytest.raises(FeedError):
        merge_feed(tmp_path, feed(snapshot()), NOW)


def test_validates_empty_but_does_not_claim_restoration(tmp_path):
    inputs(tmp_path)
    assert validate_feed(feed(), NOW) == []
    assert merge_feed(tmp_path, feed(), NOW)["imported"] == 0


def test_known_metadata_only_edition_gets_a_new_stable_corpus_id(tmp_path):
    inputs(tmp_path)
    meta = pd.read_csv(tmp_path / "tournament_metadata.csv")
    pd.concat(
        [
            meta,
            pd.DataFrame(
                [
                    {
                        "family": "New Open",
                        "year": 2026,
                        "start_date": "2026-02-02",
                        "end_date": "2026-02-03",
                    }
                ]
            ),
        ]
    ).to_csv(tmp_path / "tournament_metadata.csv", index=False)
    assert (
        merge_feed(tmp_path, feed(snapshot("New Open", 2026, "99")), NOW)["imported"]
        == 1
    )
    summary = pd.read_csv(tmp_path / "tournament_summary.csv")
    row = summary.loc[summary.family == "New Open"].iloc[0]
    assert row.tid not in [99, 5000]
    assert row.registration_source_tournament_id == 99
    assert (
        merge_feed(tmp_path, feed(snapshot("New Open", 2026, "99")), NOW)["imported"]
        == 0
    )


def test_changed_source_identity_refuses_replacing_existing_curve(tmp_path):
    inputs(tmp_path)
    merge_feed(tmp_path, feed(snapshot()), NOW)
    s = snapshot(tid="999")
    s["source_as_of"] = "2026-11-10T11:30:00.000Z"
    with pytest.raises(FeedError):
        merge_feed(tmp_path, feed(s), NOW)


def test_second_output_failure_restores_both_originals(tmp_path, monkeypatch):
    import os

    inputs(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}
    real_replace = os.replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic replacement failure")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(OSError, match="synthetic replacement"):
        merge_feed(tmp_path, feed(snapshot()), NOW)
    assert before == {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}


def test_transport_refuses_untrusted_destination_before_sending_key(monkeypatch):
    import requests
    from dataprep.registration_source import fetch_feed

    def forbidden(*args, **kwargs):
        pytest.fail("network call must not run")

    monkeypatch.setattr(requests, "get", forbidden)
    for url in [
        "https://attacker.test/cca-tourlist",
        "https://chessentries.com@attacker.test/cca-tourlist",
        "http://chessentries.com/cca-tourlist",
        "https://chessentries.com/cca-tourlist?key=value",
    ]:
        with pytest.raises(FeedError):
            fetch_feed(url, "synthetic-key")


def test_deployed_asset_router_dispatches_feed_and_previews_have_no_authority():
    import tomllib
    from pathlib import Path

    config = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "worker/wrangler.toml").read_text()
    )
    assert "/registration-feed" in config["assets"]["run_worker_first"]
    assert not config.get("previews", {}).get("services")
    assert "CCA_PROXY_KEY" not in config.get("previews", {}).get("vars", {})


def test_failed_second_replace_and_failed_rollback_can_recover_on_same_feed(
    tmp_path, monkeypatch
):
    import os

    inputs(tmp_path)
    real_replace = os.replace
    calls = 0

    def fail_second_and_restore(source, destination):
        nonlocal calls
        calls += 1
        if calls in [2, 3]:
            raise OSError("synthetic paired-output and rollback failure")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second_and_restore)
    with pytest.raises(OSError, match="rollback failure"):
        merge_feed(tmp_path, feed(snapshot()), NOW)
    # Summary was replaced, while the daily curve has not reached disk.
    assert (
        pd.read_csv(tmp_path / "tournament_summary.csv")
        .registration_source_as_of.notna()
        .sum()
        == 1
    )
    assert 5000 not in set(pd.read_csv(tmp_path / "daily_registration_counts.csv").tid)
    monkeypatch.setattr(os, "replace", real_replace)
    assert merge_feed(tmp_path, feed(snapshot()), NOW)["imported"] == 1
    assert pd.read_csv(tmp_path / "daily_registration_counts.csv").query(
        "tid == 5000"
    ).cum_regs.tolist() == [3]
    assert merge_feed(tmp_path, feed(snapshot()), NOW)["imported"] == 0


def test_live_and_pre_final_captures_do_not_enter_training_or_live_chart_corpus(
    tmp_path,
):
    from datetime import timedelta

    inputs(tmp_path)
    meta = pd.read_csv(tmp_path / "tournament_metadata.csv")
    meta.loc[meta.family == "Example Open", "end_date"] = "2026-11-10"
    meta.to_csv(tmp_path / "tournament_metadata.csv", index=False)
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}
    assert merge_feed(tmp_path, feed(snapshot()), NOW)["pending_final"] == 1
    assert before == {p.name: p.read_bytes() for p in tmp_path.glob("*.csv")}
    # A day later, that same pre-final report is still not a final capture.
    x = feed(snapshot())
    x["generated"] = "2026-11-11T12:00:00.000Z"
    assert merge_feed(tmp_path, x, NOW + timedelta(days=1))["pending_final"] == 1
    x["records"][0]["data"]["source_as_of"] = "2026-11-11T14:40:00.000Z"
    x["records"][0]["attempted_at"] = "2026-11-11T14:40:00.000Z"
    x["generated"] = "2026-11-11T15:00:00.000Z"
    assert merge_feed(tmp_path, x, NOW + timedelta(days=1, hours=3))["imported"] == 1


def test_worker_and_python_failure_reason_contracts_stay_in_sync():
    import json
    import re
    from pathlib import Path
    from dataprep.registration_contract import REASONS

    source = (
        Path(__file__).resolve().parents[1] / "worker/src/finance/registration-store.ts"
    ).read_text()
    match = re.search(r"const REASONS = new Set\((\[[\s\S]*?\])\);", source)
    assert match is not None
    producer = set(json.loads(match.group(1)))
    assert REASONS == producer | {"not_collected"}
    for reason in producer:
        x = feed(snapshot())
        x["records"][0].update(ok=False, reason=reason)
        assert validate_feed(x, NOW)[0]["reason"] == reason


def test_source_identity_survives_reconcile_and_repairs_legacy_float_encoding(tmp_path):
    from reconcile_final_counts import reconcile_final_counts

    inputs(tmp_path)
    merge_feed(tmp_path, feed(snapshot()), NOW)
    path = tmp_path / 'tournament_summary.csv'
    pd.DataFrame([{'tournament_name': '2026 Example Open', 'entry_count': 7}]).to_csv(
        tmp_path / 'daily_scrape.csv', index=False)
    reconcile_final_counts(tmp_path, verbose=False)
    summary = pd.read_csv(path, dtype={'registration_source_tournament_id': 'string'})
    assert summary.loc[summary.family == 'Example Open', 'registration_source_tournament_id'].iloc[0] == '123'
    # Reproduce the already-published numeric CSV round trip before the fix.
    pd.read_csv(path).to_csv(path, index=False)
    assert '123.0' in path.read_text()
    assert merge_feed(tmp_path, feed(snapshot()), NOW)['imported'] == 0
    pd.DataFrame([{'tournament_name': '2026 Example Open', 'entry_count': 8}]).to_csv(
        tmp_path / 'daily_scrape.csv', index=False)
    reconcile_final_counts(tmp_path, verbose=False)
    summary = pd.read_csv(path, dtype={'registration_source_tournament_id': 'string'})
    assert summary.loc[summary.family == 'Example Open', 'registration_source_tournament_id'].iloc[0] == '123.0'
    assert merge_feed(tmp_path, feed(snapshot()), NOW)['imported'] == 0
    changed = snapshot(tid='124')
    changed['source_as_of'] = '2026-11-10T11:30:00.000Z'
    with pytest.raises(FeedError):
        merge_feed(tmp_path, feed(changed), NOW)


@pytest.mark.parametrize('stored', ['123.5', '1.23e2', '123x', '0123.0'])
def test_legacy_identity_repair_is_narrow(tmp_path, stored):
    inputs(tmp_path)
    merge_feed(tmp_path, feed(snapshot()), NOW)
    path = tmp_path / 'tournament_summary.csv'
    summary = pd.read_csv(path, dtype={'registration_source_tournament_id': 'string'})
    summary.loc[summary.family == 'Example Open', 'registration_source_tournament_id'] = stored
    summary.to_csv(path, index=False)
    with pytest.raises(FeedError):
        merge_feed(tmp_path, feed(snapshot()), NOW)
