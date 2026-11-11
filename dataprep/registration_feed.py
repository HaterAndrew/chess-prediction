"""Merge verified aggregate registration curves without rebuilding the archive.

The private collector retains no player identities. Its T bins reproduce the
manual export's floor(last_reg - registered_time) rule using the same local
registration display. The calendar histogram is retained as a cross-check;
this path never rebases timestamp bins to a scrape date.
"""

import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from dataprep.registration_contract import FeedError, _require, _time, validate_feed
from dataprep.registration_source import fetch_feed
from dataprep.registration_observations import write_empty_observations
from dataprep.spikes import annotate_spikes
from tournament_aliases import canonicalize_family


PROVENANCE = "registration_source_as_of"


def _write_pair(summary_path, summary, daily_path, daily):
    """Stage both outputs; restore originals if a replacement fails.

    The pipeline publishes only after this call and its full gate succeed.
    A process kill between replacements cannot be a successful publication.
    """
    staged, originals = [], []
    try:
        for path, frame in [(summary_path, summary), (daily_path, daily)]:
            originals.append(path.read_bytes())
            with tempfile.NamedTemporaryFile(
                mode="w", dir=path.parent, prefix=".registrations-", delete=False
            ) as f:
                staged.append(Path(f.name))
                frame.to_csv(f, index=False)
                f.flush()
                os.fsync(f.fileno())
        replaced = []
        try:
            for path, temp in zip([summary_path, daily_path], staged):
                os.replace(temp, path)
                replaced.append(path)
        except OSError:
            for path, original in zip([summary_path, daily_path], originals):
                if path in replaced:
                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        dir=path.parent,
                        prefix=".registrations-restore-",
                        delete=False,
                    ) as f:
                        restore = Path(f.name)
                        f.write(original)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(restore, path)
            raise
    finally:
        for path in staged:
            path.unlink(missing_ok=True)


def _source_curve(tid, snapshot):
    curve = pd.DataFrame(snapshot["daily"]).assign(tid=int(tid))
    curve["cum_regs"] = curve.daily_regs.cumsum()
    curve["cum_pct"] = curve.cum_regs / snapshot["ts_count"]
    return curve


def _curve_matches(daily, tid, snapshot):
    """Equal provenance is a no-op only when both output files agree."""
    actual = (
        daily[daily.tid == tid].sort_values("T", ascending=False).to_dict("records")
    )
    expected = _source_curve(tid, snapshot).to_dict("records")
    if len(actual) != len(expected):
        return False
    for seen, wanted in zip(actual, expected):
        if any(seen[k] != wanted[k] for k in ["T", "daily_regs", "cum_regs"]):
            return False
        if not math.isclose(
            seen["cum_pct"], wanted["cum_pct"], rel_tol=1e-12, abs_tol=1e-12
        ):
            return False
    return True


def merge_feed(output_dir, body, now=None):
    now = now or datetime.now(timezone.utc)
    records = validate_feed(
        body, now
    )  # Validate every record before staging mutations.
    root = Path(output_dir)
    summary_path, daily_path = (
        root / "tournament_summary.csv",
        root / "daily_registration_counts.csv",
    )
    summary, daily = (
        pd.read_csv(
            summary_path, dtype={"registration_source_tournament_id": "string"}
        ),
        pd.read_csv(daily_path),
    )
    metadata = pd.read_csv(root / "tournament_metadata.csv")
    stats = dict(
        imported=0,
        preserved=0,
        stale=0,
        failed=0,
        empty=0,
        waiting=0,
        pending_final=0,
        failure_reasons={},
    )
    pending = []
    for r in records:
        if not r["ok"]:
            stats["failed"] += 1
            reason = r["reason"] or "collection_failed"
            stats["failure_reasons"][reason] = (
                stats["failure_reasons"].get(reason, 0) + 1
            )
            continue
        x = r["data"]
        if now - _time(x["source_as_of"], True) > timedelta(days=8):
            stats["stale"] += 1
            continue
        if not x["ts_count"]:
            stats["empty" if x["total"] else "waiting"] += 1
            continue
        key = canonicalize_family(r["family"]), r["year"]
        mask = (summary.family.map(canonicalize_family) == key[0]) & (
            summary.tournament_year == key[1]
        )
        _require(mask.sum() <= 1)
        meta = metadata[
            (metadata.family.map(canonicalize_family) == key[0])
            & (metadata.year == key[1])
        ]
        if mask.any():
            previous = summary.loc[summary.index[mask][0]]
            if bool(previous.has_timestamps) and pd.isna(previous.get(PROVENANCE)):
                stats["preserved"] += 1
                continue
        _require(len(meta) == 1)
        end = _time(str(meta.iloc[0]["end_date"]) + " 00:00:00").replace(
            tzinfo=timezone.utc
        )
        # Capture after the entire final local calendar day, allowing the
        # maximum 14-hour source offset. Live charts retain their scrape cohort.
        ready = end + timedelta(days=1, hours=14)
        if now < ready or _time(x["source_as_of"], True) < ready:
            stats["pending_final"] += 1
            continue
        if not mask.any():
            index = len(summary)
            # A source TID may collide with a prior synthetic roster TID.
            # Keep corpus identity independent; record source TID as provenance.
            row = {
                "tid": int(summary.tid.max()) + 1,
                "tournament_name": f"{key[1]} {key[0]}",
                "family": key[0],
                "tournament_year": key[1],
                "final_count": 0,
                "has_timestamps": False,
                "ts_count": 0,
                "is_covid": False,
                "is_online": False,
                "roster_pending": True,
            }
            summary = pd.concat([summary, pd.DataFrame([row])], ignore_index=True)
        else:
            index = summary.index[mask][0]
        original = summary.loc[index]
        provenance = original.get(PROVENANCE)
        if bool(original.has_timestamps) and pd.isna(provenance):
            stats["preserved"] += 1
            continue
        if pd.notna(provenance):
            # Older reconciliation runs inferred this nullable identifier as
            # float and wrote an exact integer ID with '.0'. Accept only that
            # known CSV encoding of the same ID, never a different identity.
            _require(
                str(original.get("registration_source_tournament_id"))
                in (x["tournament_id"], x["tournament_id"] + ".0")
            )
        if pd.notna(provenance):
            previous_source = _time(str(provenance), True)
            incoming_source = _time(x["source_as_of"], True)
            if previous_source > incoming_source:
                continue
            if previous_source == incoming_source and _curve_matches(
                daily, original.tid, x
            ):
                continue
        _require(len(meta) == 1)
        _require((summary.tid == original.tid).sum() == 1)
        pending.append((index, original, x))
    if not pending:
        write_empty_observations(root, records, now)
        return stats
    if PROVENANCE not in summary:
        summary[PROVENANCE] = pd.Series(index=summary.index, dtype="object")
        summary["registration_source_tournament_id"] = pd.Series(
            index=summary.index, dtype="object"
        )
    for index, original, x in pending:
        fields = {
            "has_timestamps": True,
            "ts_count": x["ts_count"],
            "first_reg": x["first_reg"],
            "last_reg": x["last_reg"],
            "snapshot_last_reg": x["last_reg"],
            "roster_pending": False,
            "final_count": max(int(original.final_count), x["total"]),
            PROVENANCE: x["source_as_of"],
            "registration_source_tournament_id": x["tournament_id"],
        }
        for column, value in fields.items():
            if column not in summary or (
                isinstance(value, str) and summary[column].dtype != object
            ):
                summary[column] = (
                    summary[column].astype(object)
                    if column in summary
                    else pd.Series(index=summary.index, dtype="object")
                )
            summary.at[index, column] = value
        curve = _source_curve(original.tid, x)
        daily = pd.concat(
            [daily[daily.tid != original.tid], curve[daily.columns]], ignore_index=True
        )
        target, _ = annotate_spikes(
            summary.loc[[index]].drop(
                columns=["early_bird_spike", "spike_day", "spike_magnitude"],
                errors="ignore",
            ),
            curve,
        )
        for column in ["early_bird_spike", "spike_day", "spike_magnitude"]:
            if column not in summary:
                summary[column] = pd.Series(index=summary.index, dtype="object")
            summary.at[index, column] = target.iloc[0][column]
        stats["imported"] += 1
    _write_pair(summary_path, summary, daily_path, daily)
    write_empty_observations(root, records, now)
    return stats


def source_feed_enabled(output_dir):
    """A configured collector or previously imported corpus owns this path."""
    if os.environ.get("CCA_PROXY_URL") or os.environ.get("REGISTRATION_FEED_PATH"):
        return True
    summary = pd.read_csv(Path(output_dir) / "tournament_summary.csv")
    return PROVENANCE in summary and summary[PROVENANCE].notna().any()


def refresh_feed(output_dir):
    """Use protected CI transport, or a privately collected aggregate file locally."""
    path = os.environ.get("REGISTRATION_FEED_PATH")
    if path:
        try:
            with open(path, "rb") as f:
                raw = f.read(8_000_001)
            if len(raw) > 8_000_000:
                raise FeedError("Registration feed response too large")
            body = json.loads(raw)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            raise FeedError(
                "Registration aggregate file unavailable or invalid"
            ) from None
    else:
        proxy = os.environ.get("CCA_PROXY_URL")
        if not proxy:
            raise FeedError(
                "Registration feed not configured; retained the collected corpus"
            )
        body = fetch_feed(proxy, os.environ.get("CCA_PROXY_KEY"))
    return merge_feed(output_dir, body)
