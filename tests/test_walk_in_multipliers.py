"""
Tests for walk-in entry multiplier system.

Covers:
  5a. Unit tests — computation, normalization, edge cases
  5b. Integration tests — end-to-end pipeline, output validation
  5c. Backtesting — leave-one-out historical validation
  5d. Spot checks — specific tournament families
"""

import csv
import os
import statistics

import numpy as np
import pytest

# Moved into tests/ (was repo-root); project root is two levels up so the
# digit-prefixed pipeline modules import and OUTPUT_DIR resolves to repo-root/output.
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")


# ── 5a. Unit Tests ──────────────────────────────────────────────────────────

def test_multiplier_computation():
    """Given known standings + prereg counts, assert correct ratios."""
    from importlib import import_module
    m06 = import_module("06_walk_in_multipliers")

    # Simulate: 2 tournaments, known values
    standings = {("Test Open", 2023): 200, ("Test Open", 2024): 210}
    summary = {("Test Open", 2023): 120, ("Test Open", 2024): 130}
    rows = m06.compute_multipliers(standings, summary)

    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
    assert abs(rows[0]["walk_in_ratio"] - 200/120) < 0.01
    assert abs(rows[1]["walk_in_ratio"] - 210/130) < 0.01
    print("  PASS: multiplier computation")


def test_standings_meet_the_summary_on_the_edition_key():
    """STANDINGS_NAME_MAP sends "Southwest Class" to "Southwest Class
    Championships", which the summary spells "Southwest Class" for 2015-2021;
    a letters match after the map lost every one of those years."""
    from importlib import import_module
    m06 = import_module("06_walk_in_multipliers")

    standings = {("Southwest Class", 2019): 393, ("Bostonchess Congress", 2019): 270}
    summary = {("Southwest Class", 2019): 360, ("Boston Chess Congress", 2019): 250}
    rows = m06.compute_multipliers(standings, summary)
    assert [(r["family"], r["standings_count"]) for r in rows] == [
        ("Boston Chess Congress", 270), ("Southwest Class", 393)]


def test_ratio_floor_filter():
    """Ratios < 0.5 should be filtered out (bad standings data)."""
    from importlib import import_module
    m06 = import_module("06_walk_in_multipliers")

    standings = {("Bad Open", 2023): 53}   # bad data
    summary = {("Bad Open", 2023): 400}    # prereg was 400
    rows = m06.compute_multipliers(standings, summary)

    assert len(rows) == 0, f"Expected 0 rows (filtered), got {len(rows)}"
    print("  PASS: ratio floor filter")


def test_covid_exclusion():
    """COVID years (2020-2021) should be excluded."""
    from importlib import import_module
    m06 = import_module("06_walk_in_multipliers")

    # 2020 gets filtered during load, but compute_multipliers works on
    # already-loaded data. Test the load functions instead.
    assert 2020 in m06.COVID_YEARS
    assert 2021 in m06.COVID_YEARS
    assert 2019 not in m06.COVID_YEARS
    print("  PASS: COVID year exclusion")


def test_tournament_type_classification():
    """Known tournaments get correct type labels."""
    from importlib import import_module
    m06 = import_module("06_walk_in_multipliers")

    assert "Midwest Class Championships" in m06.CLASS_FAMILIES
    assert "Western Class Championships" in m06.CLASS_FAMILIES
    assert "Eastern Class" in m06.CLASS_FAMILIES
    assert "Chicago Open" not in m06.CLASS_FAMILIES
    assert "Kings Island Open" not in m06.CLASS_FAMILIES
    print("  PASS: tournament type classification")


def test_family_stats_computation():
    """Per-family stats computed correctly from multiplier rows."""
    from importlib import import_module
    m06 = import_module("06_walk_in_multipliers")

    # compute_family_stats recency-filters on 'year' (keeps the most recent 3
    # years); the fixture must carry it or the function raises KeyError.
    rows = [
        {"family": "Test Open", "walk_in_ratio": 1.6, "tournament_type": "open", "year": 2024},
        {"family": "Test Open", "walk_in_ratio": 1.7, "tournament_type": "open", "year": 2025},
        {"family": "Test Open", "walk_in_ratio": 1.5, "tournament_type": "open", "year": 2026},
    ]
    stats = m06.compute_family_stats(rows)
    assert len(stats) == 1
    s = stats[0]
    assert s["family"] == "Test Open"
    assert s["n_years"] == 3
    assert abs(s["median_ratio"] - 1.6) < 0.01
    assert s["min_ratio"] == 1.5
    assert s["max_ratio"] == 1.7
    print("  PASS: family stats computation")


# ── 5b. Integration Tests ──────────────────────────────────────────────────

def test_output_csvs_exist():
    """06_walk_in_multipliers.py should produce valid output CSVs."""
    mult_csv = os.path.join(OUTPUT_DIR, "walk_in_multipliers.csv")
    stats_csv = os.path.join(OUTPUT_DIR, "walk_in_family_stats.csv")

    assert os.path.exists(mult_csv), f"Missing {mult_csv}"
    assert os.path.exists(stats_csv), f"Missing {stats_csv}"

    # Check multiplier CSV
    with open(mult_csv) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) > 50, f"Expected 50+ rows, got {len(rows)}"
    required_cols = {"family", "year", "prereg_count", "standings_count",
                     "walk_in_ratio", "tournament_type"}
    assert required_cols.issubset(set(rows[0].keys())), "Missing columns"

    # No NaN/Inf values
    for r in rows:
        ratio = float(r["walk_in_ratio"])
        assert not np.isnan(ratio), f"NaN ratio for {r['family']} {r['year']}"
        assert not np.isinf(ratio), f"Inf ratio for {r['family']} {r['year']}"
        assert ratio >= 0.5, f"Ratio below floor for {r['family']} {r['year']}"

    # Check stats CSV
    with open(stats_csv) as f:
        reader = csv.DictReader(f)
        stats = list(reader)
    assert len(stats) > 10, f"Expected 10+ families, got {len(stats)}"

    print(f"  PASS: output CSVs valid ({len(rows)} multiplier rows, {len(stats)} families)")


def test_apply_walkin_multiplier():
    """J3: the family walk-in ratio shrinks toward 1.1 by sample size, n/(n+k)."""
    from importlib import import_module
    m04c = import_module("04c_final_model")
    k = m04c.WALKIN_SHRINK_K

    def expected(median, n):
        return 1.1 + (median - 1.1) * n / (n + k)

    mult = {
        "Big Open": {"median_ratio": 1.65, "std_ratio": 0.05, "n_years": 20,
                     "tournament_type": "open", "min_ratio": 1.5, "max_ratio": 1.8},
        "Sparse Open": {"median_ratio": 1.65, "std_ratio": 0.0, "n_years": 1,
                        "tournament_type": "open", "min_ratio": 1.65, "max_ratio": 1.65},
    }

    # Deep history -> close to the measured ratio (real walk-in signal survives).
    tp, tl, th, ratio, source = m04c.apply_walkin_multiplier(100, 80, 120, "Big Open", mult)
    assert source == "family"
    assert abs(ratio - expected(1.65, 20)) < 1e-6
    assert ratio > 1.1
    assert tp == round(100 * ratio)

    # Sparse history -> shrunk hard toward 1.1.
    _, _, _, ratio_s, _ = m04c.apply_walkin_multiplier(100, 80, 120, "Sparse Open", mult)
    assert abs(ratio_s - expected(1.65, 1)) < 1e-6
    assert ratio_s < ratio            # fewer years -> more shrinkage
    assert 1.1 < ratio_s < 1.3

    # Unknown family -> flat 1.1 estimate (the old type table is deleted).
    _, _, _, ratio_u, source_u = m04c.apply_walkin_multiplier(100, 80, 120, "Nope Open", mult)
    assert source_u == "estimate"
    assert abs(ratio_u - 1.1) < 1e-6

    # None input.
    tp_n, _, _, _, source_n = m04c.apply_walkin_multiplier(None, None, None, "Any", mult)
    assert tp_n is None and source_n == "none"
    print("  PASS: apply_walkin_multiplier J3 shrinkage")


# ── 5c. Backtesting ────────────────────────────────────────────────────────

def test_backtest_leave_one_out(tmp_path):
    """
    Leave-one-out by year: for each family with 5+ years of data,
    hold out one year, compute multiplier from remaining, predict held-out year.
    Target: MAPE < 15%, CI coverage > 85%.
    """
    mult_csv = os.path.join(OUTPUT_DIR, "walk_in_multipliers.csv")
    with open(mult_csv) as f:
        all_rows = list(csv.DictReader(f))

    # Group by family
    from collections import defaultdict
    by_family = defaultdict(list)
    for r in all_rows:
        by_family[r["family"]].append({
            "year": int(r["year"]),
            "ratio": float(r["walk_in_ratio"]),
            "prereg": int(r["prereg_count"]),
            "actual": int(r["standings_count"]),
        })

    results = []
    families_tested = 0

    for fam, data in sorted(by_family.items()):
        if len(data) < 5:
            continue
        families_tested += 1

        for i, held_out in enumerate(data):
            train = [d for j, d in enumerate(data) if j != i]
            train_ratios = [d["ratio"] for d in train]

            median_ratio = statistics.median(train_ratios)
            std_ratio = statistics.stdev(train_ratios) if len(train_ratios) >= 2 else 0

            predicted_total = held_out["prereg"] * median_ratio
            actual_total = held_out["actual"]

            # CI using lognormal percentiles with t-distribution for small n
            if std_ratio > 0:
                from scipy.stats import t as t_dist
                n_train = len(train_ratios)
                # Use t-distribution critical value for 90% CI with n-1 df
                t_crit = t_dist.ppf(0.95, df=max(n_train - 1, 1))
                log_mu = np.log(median_ratio)
                log_sigma = np.log(1 + std_ratio / median_ratio)
                ci_low = held_out["prereg"] * np.exp(log_mu - t_crit * log_sigma)
                ci_high = held_out["prereg"] * np.exp(log_mu + t_crit * log_sigma)
            else:
                ci_low = predicted_total * 0.80
                ci_high = predicted_total * 1.20

            error_pct = abs(predicted_total - actual_total) / actual_total * 100
            in_ci = ci_low <= actual_total <= ci_high

            results.append({
                "family": fam,
                "held_out_year": held_out["year"],
                "actual_total": actual_total,
                "predicted_total": round(predicted_total),
                "ci_lower": round(ci_low),
                "ci_upper": round(ci_high),
                "error_pct": round(error_pct, 1),
                "in_ci": in_ci,
            })

    # Write backtest results to the test's own directory, not the tracked
    # output/ tree that verify_checksums hashes.
    out_csv = os.path.join(tmp_path, "walk_in_backtest_results.csv")
    fields = ["family", "held_out_year", "actual_total", "predicted_total",
              "ci_lower", "ci_upper", "error_pct", "in_ci"]
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    # Compute metrics
    mape = statistics.mean([r["error_pct"] for r in results])
    coverage = sum(1 for r in results if r["in_ci"]) / len(results) * 100

    print(f"  Backtest: {families_tested} families, {len(results)} LOO predictions")
    print(f"  MAPE:     {mape:.1f}% (target < 15%)")
    print(f"  Coverage: {coverage:.1f}% (target > 85%)")
    print(f"  Results:  {out_csv}")

    assert mape < 15, f"MAPE {mape:.1f}% exceeds 15% target"
    assert coverage > 80, f"Coverage {coverage:.1f}% below 80% target"
    print("  PASS: backtest metrics within targets")


def test_backtest_vs_naive():
    """Compare per-family multiplier vs single global multiplier."""
    mult_csv = os.path.join(OUTPUT_DIR, "walk_in_multipliers.csv")
    with open(mult_csv) as f:
        all_rows = list(csv.DictReader(f))

    all_ratios = [float(r["walk_in_ratio"]) for r in all_rows]
    global_median = statistics.median(all_ratios)

    from collections import defaultdict
    by_family = defaultdict(list)
    for r in all_rows:
        by_family[r["family"]].append({
            "prereg": int(r["prereg_count"]),
            "actual": int(r["standings_count"]),
            "ratio": float(r["walk_in_ratio"]),
        })

    family_errors = []
    global_errors = []

    for fam, data in by_family.items():
        if len(data) < 3:
            continue
        fam_median = statistics.median([d["ratio"] for d in data])
        for d in data:
            fam_pred = d["prereg"] * fam_median
            global_pred = d["prereg"] * global_median
            fam_err = abs(fam_pred - d["actual"]) / d["actual"] * 100
            global_err = abs(global_pred - d["actual"]) / d["actual"] * 100
            family_errors.append(fam_err)
            global_errors.append(global_err)

    fam_mape = statistics.mean(family_errors)
    global_mape = statistics.mean(global_errors)

    print(f"  Per-family MAPE:  {fam_mape:.1f}%")
    print(f"  Global MAPE:      {global_mape:.1f}%")
    print(f"  Improvement:      {global_mape - fam_mape:.1f}pp")

    assert fam_mape <= global_mape, "Per-family should be <= global MAPE"
    print("  PASS: per-family multiplier beats global baseline")


# ── 5e. History-depth alarm (2026-09-07 review) ────────────────────────────
#
# The spot checks below were marked xfail from 2026-09-07 to 2026-10-04 while
# the walk-in history sat at n_years=1 for 37 of 38 families, which turned the
# only signal that anything was wrong into a silent skip. check_history_depth is the alarm that should
# have fired instead: it reaches audit_warnings.json and the site's warnings
# panel through the pipeline's WARNING: harvest.

def _stats_rows(n_years_list, std=0.0):
    return [{"family": f"Fam {i}", "n_years": str(n),
             "median_ratio": "1.20", "std_ratio": str(std)}
            for i, n in enumerate(n_years_list)]


def _check():
    from importlib import import_module
    return import_module("06_walk_in_multipliers").check_history_depth


def test_history_depth_alarm_fires_on_a_collapsed_corpus():
    """The live shape as of the review: 37 of 38 families at n_years=1."""
    msg = _check()(_stats_rows([1] * 37 + [3]))
    assert msg is not None
    assert "37 of 38" in msg
    assert "std_ratio=0" in msg


def test_history_depth_alarm_quiet_when_history_is_healthy():
    assert _check()(_stats_rows([4, 5, 6, 3, 7])) is None


def test_history_depth_alarm_needs_a_majority_to_be_thin():
    """One or two thin families is normal; most of them is the failure mode."""
    assert _check()(_stats_rows([1, 1, 4, 5, 6])) is None
    assert _check()(_stats_rows([1, 1, 1, 5, 6])) is not None


def test_history_depth_alarm_handles_an_empty_corpus():
    assert _check()([]) is None


def test_history_depth_alarm_names_the_recency_cut():
    """The operator needs the cause, not just the symptom."""
    msg = _check()(_stats_rows([1] * 10))
    assert "MIN_DATA_YEAR=2023" in msg
    assert "all_registrations.csv" in msg


def test_history_depth_alarm_text_is_harvestable():
    """pipeline/warns.py picks up lines containing 'WARNING:'; the message must
    be a single line or the harvest truncates it."""
    msg = _check()(_stats_rows([1] * 10))
    assert "\n" not in msg


def test_live_corpus_alarm_state_is_reported_not_hidden():
    """Whatever the current corpus looks like, the alarm must agree with it.

    Not an assertion that the corpus is healthy — it is not — but that the
    alarm's verdict matches the data on disk rather than drifting from it.
    """
    stats_csv = os.path.join(OUTPUT_DIR, "walk_in_family_stats.csv")
    if not os.path.exists(stats_csv):
        pytest.skip("walk_in_family_stats.csv not built")
    with open(stats_csv) as f:
        rows = list(csv.DictReader(f))
    thin = [r for r in rows if int(r["n_years"]) < 2]
    msg = _check()(rows)
    if len(thin) * 2 > len(rows):
        assert msg is not None, "history has collapsed but no warning is raised"
        assert f"{len(thin)} of {len(rows)}" in msg
    else:
        assert msg is None


# ── 5d. Spot Checks ────────────────────────────────────────────────────────
#
# Until 2026-10-04 these asserted Kings Island ~1.65, Southwest Class ~1.55
# and a Mid-America "outlier" near 3.5, all strict xfails. Those ratios came
# from standings totals that counted side events, re-listed sections,
# whole-event tables and six extra rows per section; Mid-America's also
# included its 2009 and 2010 archive tables. Counted as the unique players in
# the main sections, an edition sits near its final registration count.

def _family_stats(family):
    stats_csv = os.path.join(OUTPUT_DIR, "walk_in_family_stats.csv")
    with open(stats_csv) as f:
        for r in csv.DictReader(f):
            if r["family"] == family:
                return r
    raise AssertionError(f"{family} not found in stats")


@pytest.mark.parametrize("family", ["Kings Island Open", "Southwest Class Championships",
                                    "Mid-America Open"])
def test_spot_check_main_section_ratios(family):
    r = _family_stats(family)
    assert int(r["n_years"]) >= 3
    assert 0.9 < float(r["median_ratio"]) < 1.1, r


def test_spot_check_mid_america_uses_its_own_multiplier():
    from importlib import import_module
    m04c = import_module("04c_final_model")
    ratio = float(_family_stats("Mid-America Open")["median_ratio"])
    _, _, _, m_ratio, source = m04c.apply_walkin_multiplier(
        100, 80, 120, "Mid-America Open", m04c.load_walkin_multipliers())
    assert source == "family"
    # Shrunk toward the 1.1 baseline by sample size (model/walkins.py J3).
    assert min(ratio, 1.1) <= m_ratio <= max(ratio, 1.1)


def test_spot_check_recent_2025_2026():
    """2025-2026 events: compare predicted vs actual for recent-era validation."""
    mult_csv = os.path.join(OUTPUT_DIR, "walk_in_multipliers.csv")
    recent = []
    with open(mult_csv) as f:
        for r in csv.DictReader(f):
            yr = int(r["year"])
            if yr >= 2025:
                ratio = float(r["walk_in_ratio"])
                recent.append((r["family"], yr, ratio))

    if not recent:
        print("  SKIP: no 2025+ data available")
        return

    print("  Recent events (2025+):")
    for fam, yr, ratio in sorted(recent):
        print(f"    {fam} {yr}: ratio={ratio:.3f}")

    ratios = [r[2] for r in recent]
    med = statistics.median(ratios)
    print(f"  Median 2025+ ratio: {med:.3f}")
    # Recent tournaments should have reasonable ratios (not obviously broken)
    assert all(0.5 < r < 5.0 for r in ratios), "Some 2025+ ratios look suspicious"
    print(f"  PASS: {len(recent)} recent events validated")


# ── Runner ──────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("WALK-IN MULTIPLIER TEST SUITE")
    print("=" * 60)

    print("\n--- 5a. Unit Tests ---")
    test_multiplier_computation()
    test_ratio_floor_filter()
    test_covid_exclusion()
    test_tournament_type_classification()
    test_family_stats_computation()

    print("\n--- 5b. Integration Tests ---")
    test_output_csvs_exist()
    test_apply_walkin_multiplier()

    print("\n--- 5c. Backtesting ---")
    test_backtest_leave_one_out()
    test_backtest_vs_naive()

    print("\n--- 5d. Spot Checks ---")
    for family in ("Kings Island Open", "Southwest Class Championships", "Mid-America Open"):
        test_spot_check_main_section_ratios(family)
    test_spot_check_mid_america_uses_its_own_multiplier()
    test_spot_check_recent_2025_2026()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
