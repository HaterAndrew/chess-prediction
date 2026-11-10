"""Closed aggregate registration-feed schema and conservation checks."""

import re
from datetime import datetime, timedelta, timezone

from tournament_aliases import canonicalize_family


class FeedError(ValueError):
    """A safe diagnostic with no source body, credential or customer data."""


FIELDS = {
    "version",
    "family",
    "year",
    "tournament_id",
    "source_as_of",
    "active",
    "withdrawn",
    "total",
    "ts_count",
    "first_reg",
    "last_reg",
    "daily",
    "calendar_daily",
}
RECORD_FIELDS = {"family", "year", "attempted_at", "ok", "reason", "data"}
REASONS = {
    "not_collected",
    "source_session_required",
    "source_login_expired",
    "source_login_failed",
    "source_request_limit",
    "source_network_failed",
    "source_timeout",
    "source_http_failed",
    "source_destination_refused",
    "source_incomplete",
    "source_too_many_rows",
    "source_changed_during_read",
    "registration_schema_changed",
    "registration_time_invalid",
    "registration_timestamps_missing",
    "registration_identity_invalid",
    "unmapped_tournament",
    "ambiguous_tournament",
    "incompatible_edition",
    "source_schema_changed",
    "registration_cache_invalid",
    "collection_failed",
}


def _require(condition):
    if not condition:
        raise FeedError("Registration feed contract invalid")


def _integer(value, maximum=10_000):
    return type(value) is int and 0 <= value <= maximum


def _time(value, utc=False):
    pattern = (
        r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z"
        if utc
        else r"20\d\d-\d\d-\d\d \d\d:\d\d:\d\d"
    )
    _require(isinstance(value, str) and re.fullmatch(pattern, value))
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise FeedError("Registration feed date invalid") from None


def _snapshot(x, family, year, now):
    _require(
        isinstance(x, dict)
        and set(x) == FIELDS
        and type(x["version"]) is int
        and x["version"] == 1
    )
    _require(
        x["family"] == family
        and x["year"] == year
        and isinstance(x["tournament_id"], str)
        and re.fullmatch(r"\d{1,12}", x["tournament_id"])
    )
    source = _time(x["source_as_of"], True)
    _require(source <= now + timedelta(minutes=5))
    _require(all(_integer(x[k]) for k in ["active", "withdrawn", "total", "ts_count"]))
    _require(x["active"] + x["withdrawn"] == x["total"] and x["ts_count"] <= x["total"])
    _require(
        isinstance(x["daily"], list)
        and isinstance(x["calendar_daily"], list)
        and len(x["daily"]) <= 2000
        and len(x["calendar_daily"]) <= 2000
    )
    if x["ts_count"] == 0:
        _require(
            x["total"] == 0
            and x["first_reg"] is None
            and x["last_reg"] is None
            and not x["daily"]
            and not x["calendar_daily"]
        )
        return
    first, last = _time(x["first_reg"]), _time(x["last_reg"])
    _require(first <= last <= source.replace(tzinfo=None) + timedelta(hours=14))
    previous, total = 10_001, 0
    for b in x["daily"]:
        _require(isinstance(b, dict) and set(b) == {"T", "daily_regs"})
        _require(
            _integer(b["T"])
            and b["T"] < previous
            and _integer(b["daily_regs"])
            and b["daily_regs"] > 0
        )
        previous = b["T"]
        total += b["daily_regs"]
    _require(
        total == x["ts_count"]
        and previous == 0
        and x["daily"][0]["T"] == (last - first).days
    )
    previous, total = "", 0
    for b in x["calendar_daily"]:
        _require(
            isinstance(b, dict)
            and set(b) == {"date", "daily_regs"}
            and isinstance(b["date"], str)
        )
        _time(b["date"] + " 00:00:00")
        _require(
            len(b["date"]) == 10
            and b["date"] > previous
            and _integer(b["daily_regs"])
            and b["daily_regs"] > 0
        )
        previous = b["date"]
        total += b["daily_regs"]
    _require(
        total == x["ts_count"]
        and x["calendar_daily"][0]["date"] == first.date().isoformat()
        and previous == last.date().isoformat()
    )


def validate_feed(body, now=None):
    now = now or datetime.now(timezone.utc)
    _require(
        isinstance(body, dict)
        and set(body) == {"version", "generated", "records"}
        and type(body["version"]) is int
        and body["version"] == 1
    )
    generated = _time(body["generated"], True)
    _require(now - timedelta(days=1) <= generated <= now + timedelta(minutes=5))
    _require(isinstance(body["records"], list) and len(body["records"]) <= 2000)
    seen = set()
    for r in body["records"]:
        _require(
            isinstance(r, dict) and set(r) == RECORD_FIELDS and type(r["ok"]) is bool
        )
        _require(
            isinstance(r["family"], str)
            and 0 < len(r["family"]) <= 200
            and _integer(r["year"], 2035)
            and r["year"] >= 2020
        )
        key = canonicalize_family(r["family"]), r["year"]
        _require(key not in seen)
        seen.add(key)
        if r["attempted_at"] is not None:
            _require(_time(r["attempted_at"], True) <= now + timedelta(minutes=5))
        _require(
            r["reason"] is None
            or isinstance(r["reason"], str)
            and r["reason"] in REASONS
        )
        _require(
            not r["ok"]
            or r["reason"] is None
            and r["data"] is not None
            and r["attempted_at"] is not None
        )
        if r["data"] is not None:
            _snapshot(r["data"], r["family"], r["year"], now)
    return body["records"]
