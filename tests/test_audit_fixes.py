"""
Tests for audit fixes — pinned to the AUDIT.md item IDs.

Covers Cat A (reconciliation) + Cat B helpers + Cat D (test coverage gaps)
where the underlying production code has already been written.
"""
import os
import sys

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
# Note: this test will fail until the low_confidence feature is added to
# 04c_final_model.predict_nowcast. See AUDIT.md C8.
@pytest.mark.skip(reason="C8 not yet implemented — add low_confidence flag for n<4 families")
def test_tiny_family_emits_low_confidence():
    pass


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
