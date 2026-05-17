"""
Pace alerts: compare current registration counts to historical expectations.

Called by auto_update.py during the daily pipeline. Computes pace alerts for
each live tournament and injects them into website_data.json so the front-end
can display colored badges and banners without a backend server.
"""

from datetime import datetime


def _at_T_historical_avg(tournament, all_tournaments):
    """Find the average historical count at the same T (days_before_event)
    as the current tournament's days_remaining.

    Looks up every prior edition of the same family in all_tournaments
    that has multi-point daily_data, picks the daily point nearest to
    target_T, and averages those values. Returns (avg, n_years) or
    (None, 0) if we don't have enough real data.

    This is the at-T comparator. Previous _historical_expected used
    avg_final * curve_pct which, for events whose scrape diverges from
    final count (Cleveland Open: scrape captures ~30% of final), wildly
    overstates expected and produces false "below pace" readings.
    """
    family = tournament.get("family")
    target_T = tournament.get("days_remaining")
    if family is None or target_T is None:
        return None, 0
    values = []
    for other in all_tournaments:
        if other.get("family") != family:
            continue
        if other.get("status") != "historical":
            continue
        dd = other.get("daily_data") or []
        if len(dd) < 2:
            continue
        max_day = dd[-1][0]
        best_y, best_dist = None, float("inf")
        for p in dd:
            T = max_day - p[0]
            dist = abs(T - target_T)
            if dist < best_dist:
                best_dist = dist
                best_y = p[1]
        if best_y is not None:
            values.append(best_y)
    if len(values) < 2:
        return None, 0
    return sum(values) / len(values), len(values)


def compute_pace_alerts(website_data):
    """Compute pace alerts for all live tournaments.

    Compares current_count to the average historical count at the same T
    using real per-year daily_data when available. Falls through with no
    alert when we don't have at least 2 years of real at-T data.

    Returns a list of alert dicts:
        {family, status, actual, expected, deviation_pct, message}
    """
    alerts = []
    tournaments = website_data.get("tournaments", [])

    for t in tournaments:
        if t.get("status") != "live":
            continue

        actual = t.get("current_count", 0)
        expected, n_years = _at_T_historical_avg(t, tournaments)

        if expected is None or expected <= 0:
            continue

        deviation = (actual - expected) / expected
        deviation_pct = round(deviation * 100, 1)
        n_label = f"{n_years}-year"

        if actual > expected * 1.2:
            status = "above_pace"
            msg = f"Registrations are {abs(deviation_pct)}% above {n_label} at-this-point pace"
        elif actual < expected * 0.8:
            status = "below_pace"
            msg = f"Registrations are {abs(deviation_pct)}% below {n_label} at-this-point pace"
        else:
            status = "on_pace"
            msg = f"Registrations are tracking within normal range vs {n_label} at-this-point pace ({deviation_pct:+.0f}%)"

        alerts.append({
            "family": t["family"],
            "status": status,
            "actual": actual,
            "expected": round(expected),
            "deviation_pct": deviation_pct,
            "message": msg,
        })

    return alerts


def inject_alerts(website_data, alerts):
    """Add an alerts array to the website JSON and per-tournament alert fields."""
    # Top-level alerts array
    website_data["alerts"] = alerts

    # Tag only live tournaments with their alert (if any)
    alert_by_family = {a["family"]: a for a in alerts}
    for t in website_data.get("tournaments", []):
        family = t.get("family")
        if t.get("status") == "live" and family in alert_by_family:
            t["pace_alert"] = alert_by_family[family]
        else:
            t.pop("pace_alert", None)

    return website_data
