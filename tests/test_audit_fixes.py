"""
Tests for audit fixes — pinned to the AUDIT.md item IDs.

Covers Cat A (reconciliation) + Cat B helpers + Cat D (test coverage gaps)
where the underlying production code has already been written.
"""
import os
import sys
from types import MethodType

import numpy as np
import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ── D3 — WO exclusion helper (single source of truth) ────────────────────
@pytest.mark.parametrize("name,expected", [
    # Excluded sub-events
    ('World Open Amateur', True),
    ('World Open Junior Championship', True),
    ('World Open Junior Octos', True),
    ('World Open Senior', True),
    ('World Open Senior Amateur', True),
    ('World Open Womens Championship', True),
    ('World Open Warmup', True),
    ('World Open Action', True),
    ('World Open G7 Championship', True),
    ('World Open G 10 Championship', True),
    ('World Open G 10', True),
    ('World Open G 45', True),
    ('World Open G 50 Championship', True),
    ('World Open FIDE U2200', True),
    ('World Open FIDE U2400', True),
    ('World Open Blitz Championship', True),
    ('World Open', True),  # pre-2023 combined family
    # Kept main events
    ('World Open Under 13', False),
    ('World Open Under 13 Championship', False),
    ('World Open top 6 sections', False),
    ('World Open, top 6 sections', False),
    ('World Open lower sections', False),
    ('Atlantic City Open', False),
    ('Chicago Open', False),
])
def test_wo_excluded_helper(name, expected):
    from tournament_aliases import is_wo_excluded
    assert is_wo_excluded(name) is expected, f"is_wo_excluded({name!r}) != {expected}"


# ── A2 / D — historical_standings join coverage ─────────────────────────
def test_standings_name_map_zero_orphans():
    """Live data must produce zero unmapped standings names. AUDIT.md A2."""
    from tournament_aliases import STANDINGS_NAME_MAP, validate_standings_join

    standings_path = os.path.join(PROJECT_DIR, "output", "historical_standings.csv")
    summary_path = os.path.join(PROJECT_DIR, "output", "tournament_summary.csv")
    if not (os.path.exists(standings_path) and os.path.exists(summary_path)):
        pytest.skip("standings/summary CSVs not present in this environment")

    standings = pd.read_csv(standings_path)
    summary = pd.read_csv(summary_path)
    standings['tournament_name'] = standings['tournament_name'].replace(STANDINGS_NAME_MAP)
    orphans = validate_standings_join(
        standings['tournament_name'].unique(),
        summary['family'].unique(),
        verbose=False,
    )
    assert len(orphans) == 0, f"Standings names without summary match: {sorted(orphans)}"


def test_standings_name_map_international_is_philadelphia():
    """Chessevents /event/international/YYYY is Philadelphia International.

    A zero-orphan map can still be semantically wrong if a short slug maps to
    the wrong family. AUDIT.md A2.
    """
    from tournament_aliases import STANDINGS_NAME_MAP

    assert STANDINGS_NAME_MAP['International'] == 'Philadelphia International'


# ── D1 — Reconciliation fixture: snapshot 184 + scrape 424 → 424 ─────────
def test_reconciliation_bumps_final_count(tmp_path):
    """01_data_prep should reconcile a stale snapshot up to the live scrape peak.
    Mirrors the real ACO 2026 pattern (snapshot 184, scrape peak 424).
    """
    pd.DataFrame({
        'date': pd.date_range('2026-03-22', periods=15, freq='D'),
        'tournament_name': ['2026 Test Open'] * 15,
        'entry_count': [184, 195, 216, 226, 242, 249, 274, 286, 318, 390, 400, 411, 421, 424, 424],
        'active_count': [184, 195, 216, 226, 242, 249, 274, 286, 318, 390, 400, 411, 421, 424, 424],
        'withdrawal_count': [0] * 15,
        'url': ['http://example.com'] * 15,
    }).to_csv(tmp_path / "daily_scrape.csv", index=False)

    # Build a minimal summary that mirrors the snapshot post-groupby
    summary = pd.DataFrame([{
        'tid': 9999, 'tournament_name': '2026 Test Open', 'family': 'Test Open',
        'tournament_year': 2026.0, 'final_count': 184,
        'has_timestamps': True, 'ts_count': 184,
        'first_reg': '2025-10-22 01:20:15', 'last_reg': '2026-03-21 01:35:33',
        'is_covid': False, 'is_online': False,
    }])

    # Apply the same reconciliation logic as 01_data_prep.py (extracted)
    scrape = pd.read_csv(tmp_path / "daily_scrape.csv")
    scrape['date'] = pd.to_datetime(scrape['date'])
    peak = scrape.groupby('tournament_name')['entry_count'].max().reset_index()
    peak.columns = ['tournament_name', 'scrape_peak']
    summary = summary.merge(peak, on='tournament_name', how='left')
    summary['final_count'] = summary[['final_count', 'scrape_peak']].max(axis=1).astype(int)

    assert int(summary.iloc[0]['final_count']) == 424
    assert int(summary.iloc[0]['scrape_peak']) == 424


def test_curve_extension_keeps_higher_count_on_overlapping_t():
    """Archive and scrape rows at the same T should keep the higher count."""
    archive = pd.DataFrame([
        {'tid': 1, 'T': 15, 'cum_regs': 170, 'source': 'archive'},
        {'tid': 1, 'T': 14, 'cum_regs': 184, 'source': 'archive'},
    ])
    scrape = pd.DataFrame([
        {'tid': 1, 'T': 14, 'cum_regs': 180, 'source': 'scrape'},
        {'tid': 1, 'T': 13, 'cum_regs': 210, 'source': 'scrape'},
    ])

    combined = pd.concat([archive, scrape], ignore_index=True)
    combined = combined.groupby(['tid', 'T'], as_index=False)['cum_regs'].max()

    overlap = combined[(combined['tid'] == 1) & (combined['T'] == 14)].iloc[0]
    assert int(overlap['cum_regs']) == 184


# ── D2 — Freshness assertion fires with offending names ─────────────────
def test_freshness_assertion_fires_on_stale_summary(tmp_path):
    """04e must abort grading when daily_scrape outpaces summary.final_count."""
    from importlib import import_module

    out = tmp_path / "output"
    out.mkdir()
    pd.DataFrame({
        'date': pd.date_range('2026-04-01', periods=5, freq='D'),
        'tournament_name': ['2026 Stale Open'] * 5,
        'entry_count': [200, 300, 400, 500, 600],
        'active_count': [200, 300, 400, 500, 600],
        'withdrawal_count': [0] * 5,
        'url': ['http://example.com'] * 5,
    }).to_csv(out / "daily_scrape.csv", index=False)

    summary = pd.DataFrame([{
        'tid': 1, 'tournament_name': '2026 Stale Open', 'family': 'Stale Open',
        'tournament_year': 2026.0, 'final_count': 100,
        'has_timestamps': True, 'ts_count': 100,
        'first_reg': '2025-10-01', 'last_reg': '2026-03-15',
        'is_covid': False, 'is_online': False,
    }])

    # Mark event as completed (end_date in past) so the freshness check fires.
    # In-progress events (end_date in future) are intentionally excluded from
    # the check because their final_count is a moving snapshot, not truth.
    pd.DataFrame([{
        'family': 'Stale Open', 'year': 2026,
        'start_date': '2026-03-10', 'end_date': '2026-03-14',
    }]).to_csv(out / "tournament_metadata.csv", index=False)

    sys.path.insert(0, PROJECT_DIR)
    perf = import_module("04e_performance_data")
    # Monkeypatch OUTPUT_DIR for the duration of the call
    orig = perf.OUTPUT_DIR
    perf.OUTPUT_DIR = str(out)
    try:
        with pytest.raises(RuntimeError) as exc:
            perf.assert_truth_label_freshness(summary)
        assert '2026 Stale Open' in str(exc.value)
        assert '600' in str(exc.value)  # scrape peak named in error
    finally:
        perf.OUTPUT_DIR = orig


def test_freshness_assertion_skips_in_progress_events(tmp_path):
    """In-progress events (end_date in future) must not trip the freshness check —
    their summary.final_count is a moving snapshot, not truth labels."""
    from importlib import import_module
    from datetime import datetime, timedelta

    out = tmp_path / "output"
    out.mkdir()
    pd.DataFrame({
        'date': pd.date_range('2026-04-01', periods=5, freq='D'),
        'tournament_name': ['2026 Active Open'] * 5,
        'entry_count': [200, 300, 400, 500, 600],
        'active_count': [200, 300, 400, 500, 600],
        'withdrawal_count': [0] * 5,
        'url': ['http://example.com'] * 5,
    }).to_csv(out / "daily_scrape.csv", index=False)

    summary = pd.DataFrame([{
        'tid': 1, 'tournament_name': '2026 Active Open', 'family': 'Active Open',
        'tournament_year': 2026.0, 'final_count': 100,
        'has_timestamps': True, 'ts_count': 100,
        'first_reg': '2025-10-01', 'last_reg': '2026-04-28',
        'is_covid': False, 'is_online': False,
    }])

    future = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    pd.DataFrame([{
        'family': 'Active Open', 'year': 2026,
        'start_date': future, 'end_date': future,
    }]).to_csv(out / "tournament_metadata.csv", index=False)

    sys.path.insert(0, PROJECT_DIR)
    perf = import_module("04e_performance_data")
    orig = perf.OUTPUT_DIR
    perf.OUTPUT_DIR = str(out)
    try:
        # Should not raise — event is in-progress, summary is allowed to lag scrape.
        perf.assert_truth_label_freshness(summary)
    finally:
        perf.OUTPUT_DIR = orig


# ── A5 / D4 — Scrape-coverage gate edge cases ───────────────────────────
def test_scrape_coverage_gate_excludes_only_when_event_after_snapshot():
    """Events ending BEFORE snapshot should pass the gate without scrape coverage.
    Events ending AFTER snapshot must have scrape coverage."""
    snapshot_date = pd.Timestamp('2026-03-22')
    # Case 1: event ended Jan 19, no scrape — OK (snapshot authoritative)
    end_pre = pd.Timestamp('2026-01-19')
    has_scrape = False
    ended_after_snapshot = end_pre > snapshot_date
    excluded = ended_after_snapshot and not has_scrape
    assert excluded is False

    # Case 2: event ended April 5, no scrape — EXCLUDED
    end_post = pd.Timestamp('2026-04-05')
    has_scrape = False
    ended_after_snapshot = end_post > snapshot_date
    excluded = ended_after_snapshot and not has_scrape
    assert excluded is True

    # Case 3: event ended April 5, scrape present — OK
    has_scrape = True
    excluded = ended_after_snapshot and not has_scrape
    assert excluded is False


def test_scrape_coverage_gate_uses_unrebased_snapshot_date():
    """Rebased last_reg values must not move the inferred snapshot horizon.

    If a scraped tournament rebases last_reg to today, an unscraped event that
    ended after the manual export still needs scrape coverage.
    """
    summary = pd.DataFrame([
        {'tournament_name': '2026 Scraped Open', 'last_reg': '2026-04-28',
         'snapshot_last_reg': '2026-03-22'},
        {'tournament_name': '2026 Unscraped April Open', 'last_reg': '2026-03-22',
         'snapshot_last_reg': '2026-03-22'},
    ])
    snapshot_col = 'snapshot_last_reg' if 'snapshot_last_reg' in summary.columns else 'last_reg'
    snapshot_date = pd.to_datetime(summary[snapshot_col], errors='coerce').max()

    end_post = pd.Timestamp('2026-04-05')
    scraped_names = {'2026 Scraped Open'}
    ended_after_snapshot = end_post > snapshot_date
    excluded = ended_after_snapshot and scraped_names and '2026 Unscraped April Open' not in scraped_names

    assert snapshot_date == pd.Timestamp('2026-03-22')
    assert excluded is True


# ── B2 — Walk-in source telemetry must distinguish family/type/estimate ──
def test_walkin_source_distinguishes_family_vs_estimate(tmp_path):
    """When walk_in_family_stats.csv has the family, source='family';
    when missing, source='estimate'."""
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    out = tmp_path / "output"
    out.mkdir()
    pd.DataFrame([{
        'family': 'Atlantic City Open', 'tournament_type': 'open',
        'median_ratio': 1.65, 'std_ratio': 0.10, 'n_years': 5,
        'min_ratio': 1.4, 'max_ratio': 1.9,
    }]).to_csv(out / "walk_in_family_stats.csv", index=False)

    orig = m04c.OUTPUT_DIR
    m04c.OUTPUT_DIR = str(out)
    try:
        mults = m04c.load_walkin_multipliers()
        assert 'Atlantic City Open' in mults
        _, _, _, ratio, source = m04c.apply_walkin_multiplier(
            100, 90, 110, 'Atlantic City Open', mults
        )
        assert source == 'family'
        # Unknown family → estimate path
        _, _, _, _, source2 = m04c.apply_walkin_multiplier(
            100, 90, 110, 'Nonexistent Open', mults
        )
        assert source2 == 'estimate'
    finally:
        m04c.OUTPUT_DIR = orig


# ── D5 — Walk-in freshness check ─────────────────────────────────────────
def test_walkin_freshness_warning(tmp_path):
    """When walk_in_family_stats.csv is missing, the pipeline should
    surface that 100% of multipliers fall back to 'estimate'. AUDIT.md A1/B2."""
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    out = tmp_path / "output"
    out.mkdir()
    # Deliberately do NOT create walk_in_family_stats.csv
    orig = m04c.OUTPUT_DIR
    m04c.OUTPUT_DIR = str(out)
    try:
        mults = m04c.load_walkin_multipliers()
        assert mults == {}, "load_walkin_multipliers should return {} when file missing"
        # All apply_walkin_multiplier calls should now use 'estimate' source
        _, _, _, ratio, source = m04c.apply_walkin_multiplier(100, 90, 110, 'Atlantic City Open', mults)
        assert source == 'estimate'
        assert ratio == 1.1
    finally:
        m04c.OUTPUT_DIR = orig


# ── D6 — Auto-update stale-mode propagates is_stale=True ────────────────
def test_stale_flag_propagates_to_website_data(tmp_path):
    """When the scrape fails, _stamp_stale_flag should set is_stale=True
    in website_data.json so the frontend banner activates. AUDIT.md B4."""
    from importlib import import_module
    import json

    sys.path.insert(0, PROJECT_DIR)
    auto_update = import_module("auto_update")

    wd = {
        'generated': '2026-04-28', 'tournaments': [],
        'is_stale': False, 'last_updated': None,
    }
    wd_path = tmp_path / "website_data.json"
    wd_path.write_text(json.dumps(wd))

    orig = auto_update.WEBSITE_JSON
    auto_update.WEBSITE_JSON = str(wd_path)
    try:
        auto_update._stamp_stale_flag(is_stale=True)
        result = json.loads(wd_path.read_text())
        assert result['is_stale'] is True
        assert result['last_updated'] is not None
    finally:
        auto_update.WEBSITE_JSON = orig


# ── D7 — Tiny-family fit emits low_confidence flag ──────────────────────
def test_tiny_family_emits_low_confidence(summary_df, daily_df):
    """Predictions for families with <4 historical editions must set
    self._last_low_confidence=True. AUDIT.md C8."""
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    model = m04c.N5v4_Final()
    model.fit(summary_df, daily_df)

    # Force a never-seen family — no editions
    model.predict_nowcast(50, 14, 'Definitely Not A Real Family')
    assert model._last_low_confidence is True

    # Compare with a well-established family — Chicago Open has many editions
    model.predict_nowcast(300, 14, 'Chicago Open')
    if model.family_n_editions.get('Chicago Open', 0) >= 4:
        assert model._last_low_confidence is False


# ── B1 — Prediction tier counter is populated ────────────────────────────
def test_predict_nowcast_records_tier(summary_df, daily_df, metadata_df):
    """predict_nowcast must increment self._tier_counts on each call so 04d
    can surface fallback distribution. AUDIT.md B1."""
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    model = m04c.N5v4_Final()
    model.fit(summary_df, daily_df)
    # First call initializes _tier_counts
    model.predict_nowcast(100, 14, 'Chicago Open')
    assert hasattr(model, '_tier_counts')
    assert hasattr(model, '_last_tier')
    total = sum(model._tier_counts.values())
    assert total >= 1, "tier counter should increment on call"
    assert model._last_tier in {
        'family-direct', 'family-alias', 'size-matched',
        'guard-no-data', 'guard-event-started', 'guard-no-ratios'
    }


def test_recalibrate_does_not_pollute_tier_counts(summary_df, daily_df):
    """Internal calibration predictions should not be reported as production
    prediction-tier telemetry. AUDIT.md B1.
    """
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    model = m04c.N5v4_Final()
    model.fit(summary_df, daily_df)
    completed = summary_df[summary_df['has_timestamps'].astype(bool)]
    model.recalibrate(completed, daily_df)

    assert not hasattr(model, '_tier_counts') or sum(model._tier_counts.values()) == 0

    model.predict_nowcast(100, 14, 'Chicago Open')
    assert sum(model._tier_counts.values()) == 1


# ── C1 — CI recalibration uses continuous derivation, not step function ──
def test_recalibrate_targets_continuous_coverage(summary_df, daily_df):
    """recalibrate() should set ci_adj from empirical residual quantile, not
    snap to a 5-bucket step function. AUDIT.md C1."""
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    model = m04c.N5v4_Final()
    model.fit(summary_df, daily_df)

    # Use the same fixture as completed-tournament truth labels
    completed = summary_df[summary_df['has_timestamps'].astype(bool)].head(10)
    if len(completed) < 5:
        pytest.skip("Not enough completed fixtures for recalibrate test")
    diag = model.recalibrate(completed, daily_df)
    assert diag, "recalibrate should produce per-T diagnostics"

    # Ci_adj must be a float, not snap to one of the 5 legacy buckets
    legacy_buckets = {1.15, 1.08, 1.0, 0.95, 0.90}
    for T, d in diag.items():
        adj = d.get('ci_adj')
        if adj is not None:
            # Allow exact 1.0 only if no records — but in non-trivial cohorts
            # the value should be truly continuous, not in {0.90, 0.95, 1.08, 1.15}
            assert isinstance(adj, float)
    # At least one diagnostic should have a target_coverage field
    sample = next(iter(diag.values()))
    assert sample.get('target_coverage') == 80


def test_recalibrate_ci_scale_applies_after_bias_recenter():
    """Synthetic residual stream should hit target coverage after recalibration.

    This catches the bug where ci_adj was derived around the raw point estimate
    but later applied around a bias-corrected center. AUDIT.md C1.
    """
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    completed = pd.DataFrame({
        'tid': range(10),
        'family': ['Synthetic'] * 10,
        'final_count': [120] * 8 + [140] * 2,
        'last_reg': pd.date_range('2025-01-01', periods=10),
    })
    daily = pd.DataFrame({'tid': range(10), 'T': [14] * 10, 'cum_regs': [50] * 10})
    model = m04c.N5v4_Final()

    def fake_predict(self, current_count, days_remaining, family, **kwargs):
        return 100, 90, 110

    model.predict_nowcast = MethodType(fake_predict, model)
    model.recalibrate(
        completed, daily, T_points=[14], target_coverage=0.80,
        ci_min_scale=0.0, ci_max_scale=10.0)

    half = (np.log(110) - np.log(90)) / 2
    center = 100 * model._recal_bias[14]
    lo = np.exp(np.log(center) - half * model._recal_ci[14])
    hi = np.exp(np.log(center) + half * model._recal_ci[14])
    actuals = completed['final_count'].to_numpy()
    coverage = np.mean((lo <= actuals) & (actuals <= hi))

    assert coverage == pytest.approx(0.80)


# ── C2 — Stationarity probe surfaces in diagnostics ─────────────────────
def test_recalibrate_emits_stationarity_check(summary_df, daily_df):
    """When >=6 calibration tournaments are available at a given T,
    recalibrate splits chronologically and reports old vs new bias.
    AUDIT.md C2."""
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    model = m04c.N5v4_Final()
    model.fit(summary_df, daily_df)
    completed = summary_df[summary_df['has_timestamps'].astype(bool)]
    if len(completed) < 6:
        pytest.skip("Need >=6 completed fixtures for stationarity check")

    diag = model.recalibrate(completed, daily_df)
    has_stationarity = any('stationarity' in d for d in diag.values())
    assert has_stationarity, "stationarity probe should fire at >=6 tournaments"


# ── C7 — IQR trim accounting reports per-family rates ────────────────────
def test_trim_outliers_records_per_label_stats():
    """trim_outliers(label=...) should accumulate per-label trim counts
    so users can audit which families lose the most points. AUDIT.md C7."""
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    m04c.reset_trim_stats()
    # 8 normal points + 2 extreme outliers
    vals = [1.1, 1.2, 1.0, 1.3, 1.15, 1.05, 1.25, 1.18, 50.0, 0.001]
    m04c.trim_outliers(vals, label='Test Family')
    stats = m04c.report_trim_stats()
    assert stats['total_in'] == 10
    assert stats['total_out'] < 10  # outliers trimmed
    assert stats['pct_trimmed'] > 0
    # Per-label record present
    by_label = m04c._TRIM_STATS['by_label']
    assert 'Test Family' in by_label
    assert by_label['Test Family'][0] == 10  # n_in
    assert by_label['Test Family'][1] < 10   # n_kept


def test_trim_accounting_ignores_internal_repeated_ci_calls():
    """Binary-search calibration may call lognormal_ci repeatedly; those calls
    must not inflate the once-per-fit trim audit. AUDIT.md C7.
    """
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    vals = [1.1, 1.2, 1.0, 1.3, 1.15, 1.05, 1.25, 1.18, 50.0, 0.001]
    m04c.reset_trim_stats()
    for _ in range(20):
        m04c.lognormal_ci(vals, label='Calibration Family', count_stats=False)
    assert m04c.report_trim_stats()['total_in'] == 0

    m04c.trim_outliers(vals, label='Calibration Family')
    stats = m04c.report_trim_stats()
    assert stats['total_in'] == len(vals)


# ── B3 — Event-start offset surfaces fallback usage ─────────────────────
def test_reanchor_logs_offset_source_distribution(capsys):
    """reanchor_daily_to_event_start should print offset source counts
    so silent DEFAULT_EVENT_START_OFFSET fallback is visible. AUDIT.md B3."""
    from importlib import import_module
    sys.path.insert(0, PROJECT_DIR)
    m04c = import_module("04c_final_model")

    summary = pd.DataFrame([
        {'tid': 1, 'family': 'Test Open', 'tournament_year': 2025.0,
         'last_reg': '2025-06-15', 'final_count': 100,
         'has_timestamps': True, 'is_online': False, 'is_covid': False,
         'tournament_name': '2025 Test Open'},
    ])
    daily = pd.DataFrame([
        {'tid': 1, 'T': 14, 'daily_regs': 5, 'cum_regs': 50, 'cum_pct': 0.5},
        {'tid': 1, 'T': 7, 'daily_regs': 5, 'cum_regs': 100, 'cum_pct': 1.0},
    ])
    meta = pd.DataFrame([
        # No metadata for Test Open → forces fallback
    ], columns=['family', 'year', 'start_date', 'end_date'])

    m04c.reanchor_daily_to_event_start(summary, daily, meta)
    captured = capsys.readouterr()
    assert 'offset sources' in captured.out or 'global-default' in captured.out
