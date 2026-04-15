"""
Pace alerts: compare current registration counts to historical expectations.

Called by auto_update.py during the daily pipeline. Computes pace alerts for
each live tournament and injects them into website_data.json so the front-end
can display colored badges and banners without a backend server.
"""

from datetime import datetime


def _historical_expected(tournament):
    """Estimate expected registrations at this point using the registration curve.

    Uses the tournament's registration_curve (cumulative % at each T) and
    historical final counts to derive what we'd expect right now.
    """
    hist = tournament.get("historical", [])
    curve = tournament.get("registration_curve", [])
    days_remaining = tournament.get("days_remaining")

    if not hist or not curve or days_remaining is None:
        return None

    # Average historical final count
    finals = [h["count"] for h in hist if h.get("count")]
    if not finals:
        return None
    avg_final = sum(finals) / len(finals)

    # Interpolate cumulative % at current days_remaining from the curve
    # curve is sorted by days_before descending (120, 90, 75, ... 0)
    sorted_curve = sorted(curve, key=lambda c: c["days_before"], reverse=True)

    pct_at_T = None
    for i, pt in enumerate(sorted_curve):
        if pt["days_before"] == days_remaining:
            pct_at_T = pt["cumulative_pct"]
            break
        if pt["days_before"] < days_remaining:
            # Interpolate between this point and the previous one
            if i == 0:
                pct_at_T = pt["cumulative_pct"]
            else:
                prev = sorted_curve[i - 1]
                curr = pt
                span = prev["days_before"] - curr["days_before"]
                if span == 0:
                    pct_at_T = curr["cumulative_pct"]
                else:
                    frac = (prev["days_before"] - days_remaining) / span
                    pct_at_T = prev["cumulative_pct"] + frac * (curr["cumulative_pct"] - prev["cumulative_pct"])
            break

    if pct_at_T is None:
        # days_remaining is beyond the curve range — use the last point
        if sorted_curve:
            pct_at_T = sorted_curve[-1]["cumulative_pct"]
        else:
            return None

    if pct_at_T <= 0:
        return None

    return avg_final * pct_at_T


def compute_pace_alerts(website_data):
    """Compute pace alerts for all live tournaments.

    Returns a list of alert dicts:
        {family, status, actual, expected, deviation_pct, message}
    """
    alerts = []
    tournaments = website_data.get("tournaments", [])

    for t in tournaments:
        if t.get("status") != "live":
            continue

        actual = t.get("current_count", 0)
        expected = _historical_expected(t)

        if expected is None or expected <= 0:
            continue

        deviation = (actual - expected) / expected
        deviation_pct = round(deviation * 100, 1)

        if actual > expected * 1.2:
            status = "above_pace"
            msg = f"Registrations are {abs(deviation_pct)}% above historical pace"
        elif actual < expected * 0.8:
            status = "below_pace"
            msg = f"Registrations are {abs(deviation_pct)}% below historical pace"
        else:
            status = "on_pace"
            msg = f"Registrations are tracking within normal range ({deviation_pct:+.0f}%)"

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
