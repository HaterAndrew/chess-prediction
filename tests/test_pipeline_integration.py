"""
Integration tests for the chess prediction pipeline.

Runs the full prediction pipeline on frozen test data:
  - Model fitting (N5v4_Final)
  - Nowcast predictions
  - CI bound invariants
  - Website JSON output schema
  - Scraped data validation (valid + invalid cases)

All tests use fixture data -- no network calls.
"""

import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on sys.path so we can import pipeline modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Lazy-import pipeline modules (they live at repo root, not in a package)
from importlib import import_module

m04c = import_module("04c_final_model")
validate = import_module("validate_scraped_data")


# ---------------------------------------------------------------------------
# Model fitting and prediction
# ---------------------------------------------------------------------------

class TestModelFitAndPredict:
    """Fit N5v4_Final on frozen data and verify prediction invariants."""

    @pytest.fixture(autouse=True)
    def _fit_model(self, summary_df, daily_df):
        """Fit the model once per test class."""
        self.model = m04c.N5v4_Final()
        self.model.fit(summary_df, daily_df)
        self.summary = summary_df
        self.daily = daily_df

    def test_model_has_ratios(self):
        """Model should extract ratios from historical tournaments."""
        assert len(self.model.ratios) > 0, "Model ratios dict is empty"
        # Chicago Open should have family-specific ratios (4 historical editions)
        assert "Chicago Open" in self.model.ratios, (
            "Chicago Open missing from model ratios"
        )

    def test_predict_returns_three_values(self):
        """predict_nowcast should return (point, lower, upper)."""
        result = self.model.predict_nowcast(180, 60, "Chicago Open")
        assert len(result) == 3, f"Expected 3-tuple, got {len(result)}"

    def test_prediction_not_null(self):
        """Predictions should not be None for a known family with data."""
        pred, lo, hi = self.model.predict_nowcast(180, 60, "Chicago Open")
        assert pred is not None, "Point estimate is None"
        assert lo is not None, "CI lower is None"
        assert hi is not None, "CI upper is None"

    def test_prediction_positive(self):
        """All prediction values should be positive numbers."""
        pred, lo, hi = self.model.predict_nowcast(180, 60, "Chicago Open")
        assert pred > 0, f"Point estimate not positive: {pred}"
        assert lo > 0, f"CI lower not positive: {lo}"
        assert hi > 0, f"CI upper not positive: {hi}"

    def test_ci_ordering(self):
        """CI bounds must satisfy: lower <= point_estimate <= upper."""
        pred, lo, hi = self.model.predict_nowcast(180, 60, "Chicago Open")
        assert lo <= pred, f"CI lower ({lo}) > point estimate ({pred})"
        assert pred <= hi, f"Point estimate ({pred}) > CI upper ({hi})"

    def test_prediction_exceeds_current_count(self):
        """With 60 days remaining, predicted final should exceed current count."""
        current = 180
        pred, lo, hi = self.model.predict_nowcast(current, 60, "Chicago Open")
        assert pred >= current, (
            f"Prediction ({pred}) below current count ({current})"
        )

    @pytest.mark.parametrize("days_remaining", [90, 60, 42, 28, 14, 7, 3, 1])
    def test_ci_ordering_at_multiple_lead_times(self, days_remaining):
        """CI invariant holds across all standard lead times."""
        pred, lo, hi = self.model.predict_nowcast(180, days_remaining, "Chicago Open")
        if pred is not None:
            assert lo <= pred <= hi, (
                f"CI violation at T-{days_remaining}: [{lo}, {pred}, {hi}]"
            )

    def test_unknown_family_falls_back(self):
        """Unknown family should fall back to size-matched or global ratios."""
        pred, lo, hi = self.model.predict_nowcast(100, 30, "Nonexistent Tournament")
        # May return None if truly no data, or a prediction from fallback
        if pred is not None:
            assert pred > 0
            assert lo <= pred <= hi

    def test_short_lead_time_near_current(self):
        """At T=1, prediction should be close to current count (ratio ~1.0)."""
        current = 800
        pred, lo, hi = self.model.predict_nowcast(current, 1, "Chicago Open")
        if pred is not None:
            # At T=1, expected ratio is near 1.0, so pred should be within 2x
            assert pred < current * 2, (
                f"T=1 prediction ({pred}) unreasonably far from current ({current})"
            )


# ---------------------------------------------------------------------------
# Template curves
# ---------------------------------------------------------------------------

class TestTemplateCurves:
    """Verify template curve construction from frozen data."""

    def test_build_template_curves(self, summary_df, daily_df):
        curves = m04c.build_template_curves(summary_df, daily_df)
        assert isinstance(curves, dict)
        # Should have a global fallback
        assert "__global__" in curves, "Missing __global__ template curve"

    def test_curve_values_in_range(self, summary_df, daily_df):
        curves = m04c.build_template_curves(summary_df, daily_df)
        for family, curve in curves.items():
            for t, pct in curve.items():
                assert 0.0 <= pct <= 1.0, (
                    f"Curve {family} at T={t}: pct={pct} outside [0, 1]"
                )


# ---------------------------------------------------------------------------
# Website JSON output
# ---------------------------------------------------------------------------

class TestWebsiteJsonSchema:
    """Verify the website_data.json output schema and content."""

    @pytest.fixture(autouse=True)
    def _build_json(self, summary_df, daily_df, metadata_df):
        model = m04c.N5v4_Final()
        model.fit(summary_df, daily_df)
        meta_lookup = m04c.load_meta_lookup(metadata_df)
        template_curves = m04c.build_template_curves(summary_df, daily_df)
        self.data = m04c.build_website_json(
            summary_df, daily_df, meta_lookup, model, template_curves
        )

    def test_top_level_keys(self):
        """JSON output must have required top-level keys."""
        required = {"generated", "model", "tournaments"}
        assert required.issubset(self.data.keys()), (
            f"Missing keys: {required - self.data.keys()}"
        )

    def test_model_name(self):
        assert self.data["model"] == "N5v4_Final"

    def test_tournaments_is_list(self):
        assert isinstance(self.data["tournaments"], list)
        assert len(self.data["tournaments"]) > 0

    def test_tournament_entry_keys(self):
        """Each tournament entry must have the core prediction fields."""
        required_keys = {
            "family", "year", "event_start", "event_end",
            "current_count", "days_remaining",
            "point_estimate", "ci_lower", "ci_upper", "ci_level",
            "historical", "registration_curve", "daily_data", "status",
        }
        for t in self.data["tournaments"]:
            missing = required_keys - set(t.keys())
            assert not missing, (
                f"Tournament {t.get('family', '?')} missing keys: {missing}"
            )

    def test_ci_invariant_in_json(self):
        """All tournaments in JSON must satisfy lower <= point <= upper."""
        for t in self.data["tournaments"]:
            lo = t["ci_lower"]
            pt = t["point_estimate"]
            hi = t["ci_upper"]
            assert lo <= pt <= hi, (
                f"{t['family']}: CI violation [{lo}, {pt}, {hi}]"
            )

    def test_positive_predictions_in_json(self):
        """All prediction values in JSON should be positive."""
        for t in self.data["tournaments"]:
            assert t["point_estimate"] > 0, (
                f"{t['family']}: point_estimate={t['point_estimate']}"
            )
            assert t["ci_lower"] > 0, (
                f"{t['family']}: ci_lower={t['ci_lower']}"
            )
            assert t["ci_upper"] > 0, (
                f"{t['family']}: ci_upper={t['ci_upper']}"
            )

    def test_year_is_2026(self):
        """All tournament entries should be year 2026."""
        for t in self.data["tournaments"]:
            assert t["year"] == 2026

    def test_status_values(self):
        """Status must be one of the known values."""
        valid_statuses = {"live", "in_progress", "complete", "unknown"}
        for t in self.data["tournaments"]:
            assert t["status"] in valid_statuses, (
                f"{t['family']}: invalid status '{t['status']}'"
            )

    def test_json_serializable(self):
        """Output must be JSON-serializable (no numpy/pandas types)."""
        try:
            json.dumps(self.data, default=str)
        except (TypeError, ValueError) as e:
            pytest.fail(f"Website JSON not serializable: {e}")


# ---------------------------------------------------------------------------
# Validation module: valid data
# ---------------------------------------------------------------------------

class TestValidateScrapedDataValid:
    """validate_scraped_data with clean fixture data should pass."""

    def test_validate_daily_scrape_passes(self, tmp_output):
        scrape_path = os.path.join(tmp_output, "daily_scrape.csv")
        report = validate.validate_daily_scrape(csv_path=scrape_path)
        assert report.passed, (
            f"Valid scrape data failed validation:\n{report.summary()}"
        )

    def test_validate_tournament_summary_passes(self, tmp_output):
        summary_path = os.path.join(tmp_output, "tournament_summary.csv")
        report = validate.validate_tournament_summary(csv_path=summary_path)
        assert report.passed, (
            f"Valid summary data failed validation:\n{report.summary()}"
        )


# ---------------------------------------------------------------------------
# Validation module: invalid data
# ---------------------------------------------------------------------------

class TestValidateScrapedDataInvalid:
    """validate_scraped_data should catch known bad data patterns."""

    def _write_csv(self, tmp_path, filename, header, rows):
        """Helper: write a CSV from header + list of row dicts."""
        path = tmp_path / filename
        import csv
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            for row in rows:
                w.writerow(row)
        return str(path)

    def test_missing_file(self, tmp_path):
        report = validate.validate_daily_scrape(
            csv_path=str(tmp_path / "nonexistent.csv")
        )
        assert not report.passed
        assert any("not found" in e.lower() for e in report.errors)

    def test_empty_file(self, tmp_path):
        path = self._write_csv(
            tmp_path, "empty.csv",
            ["date", "tournament_name", "entry_count", "url"], []
        )
        report = validate.validate_daily_scrape(csv_path=path)
        assert not report.passed
        assert any("empty" in e.lower() for e in report.errors)

    def test_negative_entry_count(self, tmp_path):
        path = self._write_csv(
            tmp_path, "neg.csv",
            ["date", "tournament_name", "entry_count", "url"],
            [{"date": "2026-03-23", "tournament_name": "Test Open",
              "entry_count": "-5", "url": "https://example.com"}],
        )
        report = validate.validate_daily_scrape(csv_path=path)
        assert not report.passed
        assert any("negative" in e.lower() for e in report.errors)

    def test_entry_count_over_limit(self, tmp_path):
        path = self._write_csv(
            tmp_path, "huge.csv",
            ["date", "tournament_name", "entry_count", "url"],
            [{"date": "2026-03-23", "tournament_name": "Test Open",
              "entry_count": "99999", "url": "https://example.com"}],
        )
        report = validate.validate_daily_scrape(csv_path=path)
        assert not report.passed
        assert any("10000" in e for e in report.errors)

    def test_malformed_date(self, tmp_path):
        path = self._write_csv(
            tmp_path, "baddate.csv",
            ["date", "tournament_name", "entry_count", "url"],
            [{"date": "03-23-2026", "tournament_name": "Test Open",
              "entry_count": "50", "url": "https://example.com"}],
        )
        report = validate.validate_daily_scrape(csv_path=path)
        assert not report.passed
        assert any("malformed" in e.lower() or "date" in e.lower()
                    for e in report.errors)

    def test_duplicate_entries(self, tmp_path):
        row = {"date": "2026-03-23", "tournament_name": "Test Open",
               "entry_count": "50", "url": "https://example.com"}
        path = self._write_csv(
            tmp_path, "dup.csv",
            ["date", "tournament_name", "entry_count", "url"],
            [row, row],
        )
        report = validate.validate_daily_scrape(csv_path=path)
        assert not report.passed
        assert any("duplicate" in e.lower() for e in report.errors)

    def test_missing_required_column(self, tmp_path):
        # Write CSV missing the 'url' column
        path = self._write_csv(
            tmp_path, "nocol.csv",
            ["date", "tournament_name", "entry_count"],
            [{"date": "2026-03-23", "tournament_name": "Test",
              "entry_count": "50"}],
        )
        report = validate.validate_daily_scrape(csv_path=path)
        assert not report.passed
        assert any("url" in e.lower() for e in report.errors)

    def test_summary_negative_final_count(self, tmp_path):
        path = self._write_csv(
            tmp_path, "badsummary.csv",
            ["tid", "tournament_name", "final_count", "tournament_year"],
            [{"tid": "999", "tournament_name": "Bad Open",
              "final_count": "-10", "tournament_year": "2025"}],
        )
        report = validate.validate_tournament_summary(csv_path=path)
        assert not report.passed
        assert any("negative" in e.lower() for e in report.errors)

    def test_summary_duplicate_tid(self, tmp_path):
        row = {"tid": "999", "tournament_name": "Dup Open",
               "final_count": "100", "tournament_year": "2025"}
        path = self._write_csv(
            tmp_path, "duptid.csv",
            ["tid", "tournament_name", "final_count", "tournament_year"],
            [row, row],
        )
        report = validate.validate_tournament_summary(csv_path=path)
        assert not report.passed
        assert any("duplicate" in e.lower() for e in report.errors)


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """Unit tests for standalone helper functions in 04c."""

    def test_lognormal_ci_basic(self):
        """lognormal_ci should return (median, lo, hi) with lo < hi."""
        ratios = [1.5, 1.8, 2.0, 1.6, 1.9]
        med, lo, hi = m04c.lognormal_ci(ratios)
        assert lo < med < hi
        assert lo > 0
        assert hi > 0

    def test_lognormal_ci_single_value(self):
        """Single ratio should return a default CI band."""
        med, lo, hi = m04c.lognormal_ci([2.0])
        assert med == 2.0
        assert lo < med < hi

    def test_trim_outliers(self):
        """trim_outliers should remove extreme values."""
        values = [1.0, 1.1, 1.2, 1.0, 1.1, 50.0]
        trimmed = m04c.trim_outliers(values)
        # The 50.0 outlier should be removed
        assert max(trimmed) < 50.0

    def test_is_complete_past_year(self):
        """Pre-2026 tournaments should be marked complete."""
        row = {"tournament_year": 2024}
        assert m04c.is_complete(row) is True

    def test_is_complete_2026(self):
        """2026 tournaments should not be complete by default."""
        row = {"tournament_year": 2026}
        assert m04c.is_complete(row) is False

    def test_determine_status_future(self):
        """Future event should be 'live'."""
        from datetime import datetime, timedelta
        future = datetime.now() + timedelta(days=30)
        info = {"start_date": future, "end_date": future + timedelta(days=4)}
        assert m04c.determine_status(info) == "live"

    def test_determine_status_past(self):
        """Past event should be 'complete'."""
        from datetime import datetime, timedelta
        past_end = datetime.now() - timedelta(days=30)
        info = {"start_date": past_end - timedelta(days=4), "end_date": past_end}
        assert m04c.determine_status(info) == "complete"
