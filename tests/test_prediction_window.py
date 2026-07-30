"""Tests for the post-start online-registration window.

Regression cover for the Chicago Open 2026 bug: on the 5-day schedule's
start_date the predictor froze the estimate at the live count (806 entries ->
"final 806"), ignoring the 4/3/2-day schedules whose online entries keep
arriving for days afterward. prediction_window keeps the model projecting
forward through that window.
"""

import pandas as pd

from prediction_window import registration_close_date, window_decayed_estimate


# ── registration_close_date ──────────────────────────────────────────────

class TestRegistrationCloseDate:
    def test_end_minus_one_day(self):
        """Close = end_date - 1 (the 2-day schedule, last online entry point)."""
        close = registration_close_date(
            pd.Timestamp("2026-05-21"), pd.Timestamp("2026-05-25"))
        assert close == pd.Timestamp("2026-05-24")

    def test_chicago_open_2026(self):
        """Chicago Open 2026: starts 05-21, ends 05-25 -> registration 05-24."""
        close = registration_close_date(
            pd.Timestamp("2026-05-21"), pd.Timestamp("2026-05-25"))
        # Three days of online registration remain on start day (05-21).
        assert (close - pd.Timestamp("2026-05-21")).days == 3

    def test_no_end_date_falls_back_to_start(self):
        """Single-schedule event (no end_date): registers up to its own start."""
        close = registration_close_date(pd.Timestamp("2026-06-01"), None)
        assert close == pd.Timestamp("2026-06-01")

    def test_never_earlier_than_start(self):
        """A 1-day event (start == end) must not close registration pre-start."""
        close = registration_close_date(
            pd.Timestamp("2026-06-01"), pd.Timestamp("2026-06-01"))
        assert close == pd.Timestamp("2026-06-01")

    def test_none_event_date(self):
        assert registration_close_date(None, pd.Timestamp("2026-05-25")) is None


# ── window_decayed_estimate ──────────────────────────────────────────────

# Chicago Open 2026 at event start: 806 online entries, T=0 ratio ~1.08 ->
# event-start prediction triple of (871, 817, 929). window_len = 3 days.
CO_CURRENT = 806
CO_T0 = (871, 817, 929)
CO_WINDOW = 3


class TestWindowDecayedEstimate:
    def test_start_day_returns_full_t0_estimate(self):
        """On the start day (days_into_window=0) decay=1: full T=0 projection."""
        point, lo, hi = window_decayed_estimate(
            CO_CURRENT, *CO_T0, days_into_window=0, window_len=CO_WINDOW)
        assert (point, lo, hi) == CO_T0

    def test_start_day_predicts_forward_not_frozen(self):
        """Regression: the bug froze the estimate at the live count on start day."""
        point, _, _ = window_decayed_estimate(
            CO_CURRENT, *CO_T0, days_into_window=0, window_len=CO_WINDOW)
        assert point > CO_CURRENT, (
            "On the 5-day start day the model must still project forward — "
            "online 4/3/2-day entries are still arriving."
        )

    def test_converges_to_current_at_close(self):
        """At registration close (days_into_window == window_len) decay=0."""
        point, lo, hi = window_decayed_estimate(
            CO_CURRENT, *CO_T0, days_into_window=CO_WINDOW, window_len=CO_WINDOW)
        assert (point, lo, hi) == (CO_CURRENT, CO_CURRENT, CO_CURRENT)

    def test_point_estimate_decreases_across_window(self):
        """The projection shrinks monotonically as registration close nears."""
        points = [
            window_decayed_estimate(
                CO_CURRENT, *CO_T0, days_into_window=d, window_len=CO_WINDOW)[0]
            for d in range(CO_WINDOW + 1)
        ]
        assert points == sorted(points, reverse=True)
        assert points[0] == CO_T0[0] and points[-1] == CO_CURRENT

    def test_never_below_current_count(self):
        """Registered entries cannot un-register — final field >= live count."""
        for d in range(CO_WINDOW + 1):
            point, lo, hi = window_decayed_estimate(
                CO_CURRENT, *CO_T0, days_into_window=d, window_len=CO_WINDOW)
            assert lo >= CO_CURRENT and point >= CO_CURRENT and hi >= CO_CURRENT

    def test_ci_lower_clamped_when_t0_lo_below_current(self):
        """A wide T=0 CI whose lower bound dips under the live count is clamped."""
        _, lo, _ = window_decayed_estimate(
            806, 900, 780, 1020, days_into_window=0, window_len=3)
        assert lo >= 806

    def test_zero_window_is_passthrough(self):
        """No post-start window (single-schedule event): no forward projection."""
        assert window_decayed_estimate(
            806, 871, 817, 929, days_into_window=0, window_len=0) == (806, 806, 806)

    def test_zero_current_count_is_passthrough(self):
        assert window_decayed_estimate(
            0, 100, 90, 110, days_into_window=0, window_len=3) == (0, 0, 0)

    def test_none_t0_point_is_passthrough(self):
        assert window_decayed_estimate(
            806, None, None, None, days_into_window=1, window_len=3) == (806, 806, 806)
