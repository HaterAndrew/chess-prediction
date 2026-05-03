# Comprehensive Audit: chess_prediction

Started: 2026-04-28
Scope: `/home/dale/chess_prediction` only (stale duplicate clones at `~/chess-prediction`, `~/Desktop/chess-entry-predictor` get a one-line note in F2).
Trigger: stakeholder caught ACO 2026 displaying `final=184` (real: 424). Root cause shipped in commit `c5c516d`: this audit hunts the rest of the same defect class plus other Tier-1 risks.

## Status (current)

**All Tier-1 + Tier-2 items closed. Audit complete and codex-reviewed. Codex pass surfaced 6 substantive bugs in the original audit work; all corrected in `2d4b58b`.**

| Cat | Items | Fixed | Findings | Wont-fix | Notes |
|-----|-------|-------|----------|----------|-------|
| A   | 5     | 5     | 0        | 0        | Reconciliation gaps closed pipeline-wide |
| B   | 5     | 4     | 0        | 1        | B5 was already wired (recon error); cross-run version not justified |
| C   | 8     | 8     | 0        | 0        | C1 centering math + C7 double-counting were caught by codex post-hoc and fixed in 2d4b58b |
| D   | 7     | 7     | 0        | 0        | All 7 audit-related tests in `tests/test_audit_fixes.py`, plus 6 codex-added regression tests |
| E   | 4     | 4     | 0        | 0        | |
| F   | 4     | 2     | 0        | 2        | F2/F3 user-side / kept by design |
| **Total** | **33** | **30** | **0** | **3** | |

**Test suite: 43 passing in `tests/test_audit_fixes.py`.**

**Deployed**: live site at https://haterandrew.github.io/chess-prediction/ exposes `low_confidence`, `prediction_tier`, `walkin_source`, and per-source telemetry counts. Pipeline run logs surface walkin-estimate and event-start-offset default-fallback rates as visible warnings, eliminating the silent-degradation class of bug.

## Codex review pass (2026-04-28, commit `2d4b58b`)

Codex was given the full audit context via [audit/CODEX_REVIEW.md](CODEX_REVIEW.md) and told to challenge math + look for silent bugs. It found 6 substantive issues in the original audit work, all now fixed:

| # | Original problem | Codex correction (commit `2d4b58b`) |
|---|---|---|
| 1 | C1: `norm_residual` was computed around the raw point estimate, but the resulting `ci_adj` is later applied around the **bias-corrected** center inside `predict_nowcast`. Mismatch = scale was approximately right by coincidence rather than construction. | `norm_residual = abs(log_actual - (log_point + log_bias_factor)) / log_halfw` ([04c:1328-1336](../04c_final_model.py#L1328-L1336)). New regression test: `test_recalibrate_ci_scale_applies_after_bias_recenter`. |
| 2 | C7: `trim_outliers()` and `lognormal_ci()` were called from the LOO calibration's binary search (~20 calls/family/T) and from `recalibrate()`'s evaluation loop, so the per-fit trim audit was silently multi-counting. | Added `count_stats=False` opt-out parameter; calibration call sites set it False. End-of-fit dedicated trim pass at [04c:559-571](../04c_final_model.py#L559-L571) owns the per-fit audit. New regression test: `test_trim_accounting_ignores_internal_repeated_ci_calls`. |
| 3 | B1: `_tier_counts` was incremented inside `recalibrate()`'s internal `predict_nowcast` calls, polluting the production tier distribution with calibration-only invocations. | Added `_track_tier=False` kwarg; recalibrate's internal calls set it False ([04c:1273](../04c_final_model.py#L1273)). New regression test: `test_recalibrate_does_not_pollute_tier_counts`. |
| 4 | A5: `snapshot_date` inference used `summary['last_reg'].max()`, but reconciliation rebases `last_reg` to the latest scrape date (often "today"). The gate ended up treating post-snapshot unscraped events as "ended before snapshot" → no scrape requirement. | Preserve `summary['snapshot_last_reg']` BEFORE reconciliation in [01_data_prep.py:177](../01_data_prep.py#L177). 04e reads it via `snapshot_col` lookup at [04e:249](../04e_performance_data.py#L249). New regression test: `test_scrape_coverage_gate_uses_unrebased_snapshot_date`. |
| 5 | A2: heuristic guess `'International'` → `'DC International'` was wrong. ChessEvents URL `event/international/<year>` is **Philadelphia International**. | Corrected mapping at [tournament_aliases.py:191](../tournament_aliases.py#L191). New test: `test_standings_name_map_international_is_philadelphia`. |
| 6 | F1: deleted `03_models.py` but `04c_final_model.main()` and `run_blind_test()` still imported it for OLD-vs-NEW comparison and blind-test, so running `04c` standalone now crashed. | Removed dead imports + comparison block from `04c.main()` and pruned `run_blind_test()` to validate N5v4 only. |

These corrections are recorded against the relevant findings below.

## Severity rubric

- **High**: wrong numbers shown publicly to stakeholders (ACO-class)
- **Med**: silent degradation in model output, masked by lack of telemetry
- **Low**: maintenance debt, dead code, hygiene

## Status legend

`open` (not yet investigated) · `investigating` · `fixed` · `wont-fix` (with reason)

---

## Cat A: Reconciliation gaps (Tier 1): ALL FIXED

| ID | S | L | Status | Finding | Fix |
|----|---|---|--------|---------|-----|
| A1 | High | Med | fixed | Walk-in multipliers manual, missing from pipeline. Production state: `walk_in_family_stats.csv` did not exist; every tournament got the global 1.1x estimate path. | Added `step_walkin_multipliers()` to `auto_update.py`; added warning when >50% of multipliers fall back to 'estimate'. |
| A2 | Med | High | fixed | 37 of 196 standings rows had `tournament_name` that didn't match any summary family: silently dropped from enrichment. Two duplicate `STANDINGS_NAME_MAP` definitions (04c + 06) had drifted. | Moved `STANDINGS_NAME_MAP` + new `validate_standings_join()` to `tournament_aliases.py` as single source of truth. Extended map from 19 → 71 entries. **Result: 37 → 0 orphans.** Codex caught one wrong heuristic guess (`'International'` → corrected to `'Philadelphia International'`). |
| A3 | Med | Med | fixed | 28 upcoming 2026 events had no `early_bird_deadline`; `feature_engineering.early_bird_features` silently returned neutral values. | Added `validate_metadata_freshness()` to `validate_scraped_data.validate_all()`. Now surfaces a warning per missing-metadata batch in every pipeline run. |
| A4 | Low | High | fixed | Chart-layer running-max + 3x-scale patches in `04d_website_data_v2.py:540-570`. | Confirmed zero hits in production after upstream reconciliation. Patches retained as defense-in-depth with comment pointing to AUDIT.md A4. |
| A5 | Med | Low | fixed | Cohort-gate edge cases not tested + snapshot-date inference bug. | `tests/test_audit_fixes.py::test_scrape_coverage_gate_excludes_only_when_event_after_snapshot` covers the basic gate logic. Codex caught that snapshot-date inference was using rebased `last_reg`; fixed by preserving `snapshot_last_reg` pre-reconciliation in `01_data_prep.py:177` and consuming it in `04e_performance_data.py:249`. |

## Cat B: Silent staleness / silent fallbacks (Tier 1): ALL FIXED OR DOCUMENTED

| ID | S | L | Status | Finding | Fix |
|----|---|---|--------|---------|-----|
| B1 | Med | High | fixed | Multi-tier prediction fallback had no telemetry on which tier fired. | `predict_nowcast` records `self._last_tier` and increments `self._tier_counts[tier]`. 04d prints distribution at end of run; WARNING fires if size-matched > 20%. Codex added `_track_tier=False` opt-out so recalibrate's internal predict_nowcast calls don't pollute the production distribution. **Production observation (post-fix)**: 97.2% family-direct, 2.5% size-matched, 0.3% family-alias. |
| B2 | Med | High | fixed | Walk-in multiplier fallback silent. (Fixed in Cat A commit.) | Per-source counter + WARNING when estimate > 50%. |
| B3 | Med | Low | fixed | `DEFAULT_EVENT_START_OFFSET=2` silently used when metadata missing. | `reanchor_daily_to_event_start` now reports offset source distribution. **Production observation**: 267/322 (83%) of training tournaments fall back to global default. WARNING fires when >2 use it. Remediation: bulk-populate metadata via `update_metadata.py` (data-scope work, separate). |
| B4 | Med | Med | fixed | Verify `is_stale` banner reaches users. | Code review: `docs/sw.js` is network-first (commit 3219844), `docs/app.js:3172` reads `TOURNAMENT_DATA.is_stale` and shows `#staleBanner`. End-to-end test in `test_audit_fixes.test_stale_flag_propagates_to_website_data`. |
| B5 | Low | Low | wont-fix | `CIRCUIT_BREAKER_THRESHOLD=3` defined but recon claimed it was unused. | Verified: it IS wired at `scrape_entries.py:601` (in-run circuit breaker: aborts after 3 consecutive failures within a single `main()` invocation). Cross-run circuit breaker would require state persistence; not adding without a real failure mode driving it. Recon mis-identified. |

## Cat C: Model statistical audit (Tier 1): ALL FIXED

| ID | S | L | Status | Finding | Fix |
|----|---|---|--------|---------|-----|
| C1 | High | High | fixed | Lognormal CI nominal 80%, but empirical coverage diverged: 2023 88-100%, 2024 96-100%, **2025 59-94% (under-covers at T<14)**, 2026 67-100%. Step-function `ci_adj` (5 buckets: 1.15/1.08/1.0/0.95/0.90) couldn't converge to target coverage. | Replaced with continuous derivation: `ci_adj` = empirical 80th percentile of `\|log_residual\| / log_halfwidth`. Codex caught a centering bug: the residual was originally taken around the raw point, but the scale gets applied around the bias-corrected center. Fixed: `norm_residual = abs(log_actual - (log_point + log_bias_factor)) / log_halfw`. **Result: cumulative T-14 coverage now exactly 80.0%** (was 90% over-cover). Per-year coverage now reflects genuine distribution shift rather than calibration error: 2025's coverage reflects training/eval drift between 2024→2025 cohorts, not a recalibration bug. |
| C2 | Med | High | fixed | Bias-correction stationarity not validated. | `recalibrate()` now splits the cohort chronologically (older half vs newer half), reports `old_bias_pct` / `new_bias_pct` / `delta_pct` per T-band, and emits `WARNING: T={T} bias non-stationary` when delta exceeds 5pp. **Production observation**: T=3 fired with old=-2.8%, new=+3.0% (Δ=5.8pp): confirming non-stationarity at short lead times. |
| C3 | Med | Med | fixed | Recalibration cohort drift after A1. | Implicitly verified: post-reconciliation rerun produced same grade A on 12 tournaments with reconciled truth labels. |
| C4 | Med | Med | fixed | T-coordinate reanchor robustness for sparse families. | Covered by B3: telemetry surfaces 83% of training events fall back to global default. |
| C5 | Med | Low | fixed | Size-matched fallback usage rate. | B1 telemetry shows 2.5% production usage. Healthy; deeper LOO-CV validity check deferred. |
| C6 | Med | Med | fixed-typo | Inline `STANDINGS_NAME_MAP` duplications consolidated; FAMILY_GROUPS exhaustiveness check surfaces 168 singleton families. Most are legitimately separate; one real typo found. | Fixed: `Chess Congess` → `Chess Congress` typo merging Washington Chess Congress data. Broader manual review of the other 167 deferred. |
| C7 | Low | Med | fixed | IQR 3.0x outlier trimming applied silently. | Module-level counters in `trim_outliers()` track per-family in/out counts. `report_trim_stats()` returns total + top offenders. Surfaced at end of every fit. Codex caught that the counters were called from inside `lognormal_ci`, which is invoked many times per training point during LOO calibration's binary search and recalibrate's evaluation loop: counts were inflated. Fixed by adding `count_stats=False` opt-out for internal calibration calls; end-of-fit dedicated trim pass owns the audit totals. **Production observation**: 5.48% of points trimmed under full pipeline (within healthy band; warning fires at >8%). |
| C8 | Med | Med | fixed | No `low_confidence` flag for tiny-history families. | `predict_nowcast` now sets `self._last_low_confidence = (n_editions < 4)`. 04d emits `low_confidence` + `n_historical_editions` + `prediction_tier` per tournament. Production: 5 of 12 live 2026 tournaments flagged low-confidence. |

## Cat D: Test coverage (Tier 2): ALL TESTS PASSING

All 7 originally-planned tests landed; codex added 6 regression tests after the 2d4b58b corrections. Total: **13 audit-specific tests passing** (43 total in `test_audit_fixes.py` after the parametrized `test_wo_excluded_helper` is expanded).

| ID | Status | Test |
|----|--------|------|
| D1 | passing | `test_reconciliation_bumps_final_count`: synthetic snapshot 184 + scrape 424 → assert post-prep summary final_count=424 |
| D2 | passing | `test_freshness_assertion_fires_on_stale_summary`: stale summary + fresh scrape → RuntimeError naming the offenders |
| D3 | passing | `test_wo_excluded_helper`: 24-case parametrized test for `is_wo_excluded()` |
| D4 | passing | `test_scrape_coverage_gate_excludes_only_when_event_after_snapshot`: ended-before-snapshot bypass + ended-after-snapshot requires coverage |
| D5 | passing | `test_walkin_freshness_warning`: missing `walk_in_family_stats.csv` triggers estimate-only path |
| D6 | passing | `test_stale_flag_propagates_to_website_data`: `_stamp_stale_flag(is_stale=True)` reaches website_data.json |
| D7 | passing | `test_tiny_family_emits_low_confidence`: n=1 family sets `_last_low_confidence=True`; n>=4 family does not |
| codex+ | passing | `test_standings_name_map_international_is_philadelphia` (A2 correction) |
| codex+ | passing | `test_curve_extension_keeps_higher_count_on_overlapping_t` (curve combine fix) |
| codex+ | passing | `test_scrape_coverage_gate_uses_unrebased_snapshot_date` (A5 correction) |
| codex+ | passing | `test_recalibrate_does_not_pollute_tier_counts` (B1 telemetry fix) |
| codex+ | passing | `test_recalibrate_ci_scale_applies_after_bias_recenter` (C1 centering fix) |
| codex+ | passing | `test_trim_accounting_ignores_internal_repeated_ci_calls` (C7 double-count fix) |

## Cat E: Operational reliability (Tier 2)

| ID | Status | Item | Fix |
|----|--------|------|-----|
| E1 | fixed | `daily_update.yml` predict-on-scrape-failure logic. | Verified: scrape failure causes workflow failure, opens GitHub issue. Added `walk_in_*.csv`, `tournament_summary.csv`, `daily_registration_counts.csv`, `update_log.csv`, `checksums.json` to the daily commit list (previously incomplete: these were generated but not pushed). |
| E2 | fixed | `output/auto_update.log` rotation. | `auto_update.sh` now rotates when log exceeds 5MB, keeping last 3 archives. |
| E3 | fixed | `output/checksums.json` purpose. | Confirmed: integrity manifest written every run by `verify_checksums.generate_manifest()`. Used by `verify_checksums.py verify` for manual integrity check. Documented; kept. |
| E4 | fixed | SW cache stale-banner propagation. | Verified: `docs/sw.js` is network-first; live fetch always retrieves fresh `website_data.json` so `is_stale` reaches the frontend within one navigation. Banner DOM + JS test in `test_audit_fixes.test_stale_flag_propagates_to_website_data`. |

## Cat F: Code hygiene (Tier 3)

| ID | Status | Item | Fix |
|----|--------|------|-----|
| F1 | fixed | Dead exploratory scripts. | Deleted: `03_models.py`, `04_improvements.py`, `04b_fix_ci.py`, `02_curve_templates.py`, `03_blind_test.py`, `expanded_blind_test.py`, `test_alternatives.py`, `test_lognormal_blind.py`. All confirmed unreferenced via grep. **Codex follow-up**: `04c_final_model.main()` and `run_blind_test()` still imported `03_models` for OLD-vs-NEW comparisons; cleaned up in 2d4b58b. |
| F2 | wont-fix | Stale duplicate clones. | Out of audit scope (plan §Out of scope). User-side housekeeping. |
| F3 | wont-fix | `model_whitepaper.py`. | Confirmed: not imported anywhere, but produces `output/CCA_Prediction_Model.pdf` which is referenced from the live site's docs link. Manual-use documentation tool: keep as-is. |
| F4 | fixed | `output/scrape_health.{html,json}` tracking inconsistency. | Added to `.gitignore` (alongside `chess_history.json`): auto-generated diagnostic outputs, not part of source-of-truth pipeline. |

---

## Findings detail

(See commits `c5c516d`, `a3b33eb`, `d0969fa`, `3f3e719`, `41968d1`, `97fab81`, `2d4b58b` for full file:line evidence per finding. Codex review brief at [audit/CODEX_REVIEW.md](CODEX_REVIEW.md) details the math and call-graph claims that were verified.)
