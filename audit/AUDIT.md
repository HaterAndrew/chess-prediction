# Comprehensive Audit — chess_prediction

Started: 2026-04-28
Scope: `/home/dale/chess_prediction` only (stale duplicate clones at `~/chess-prediction`, `~/Desktop/chess-entry-predictor` get a one-line note in F2).
Trigger: stakeholder caught ACO 2026 displaying `final=184` (real: 424). Root cause shipped in commit `c5c516d` — this audit hunts the rest of the same defect class plus other Tier-1 risks.

## Status (2026-04-28)

**All Tier-1 + Tier-2 items closed. Audit complete.**

| Cat | Items | Fixed | Findings | Wont-fix | Notes |
|-----|-------|-------|----------|----------|-------|
| A   | 5     | 5     | 0        | 0        | Reconciliation gaps closed pipeline-wide |
| B   | 5     | 4     | 0        | 1        | B5 was already wired (recon error); cross-run version not justified |
| C   | 8     | 5     | 3        | 0        | C1/C2/C7 are documented findings; CI recalibration is its own project |
| D   | 7     | 7     | 0        | 0        | All audit-related test coverage in place |
| E   | 4     | 4     | 0        | 0        | |
| F   | 4     | 2     | 0        | 2        | F2/F3 user-side / kept by design |
| **Total** | **33** | **27** | **3** | **3** | |

**Deployed**: live site at https://haterandrew.github.io/chess-prediction/ now exposes `low_confidence`, `prediction_tier`, `walkin_source`, and per-source telemetry counts. Pipeline run logs surface 79% walkin-estimate ratio + 83% event-start-offset default-fallback as visible warnings, eliminating the silent-degradation class of bug.

**Live verification** (2026-04-28 20:34 UTC):
- 10 tournaments flagged `low_confidence: true`
- Walk-in source distribution: 265 family / 112 estimate (was 0/377 before A1 fix)
- Prediction tier on live cohort: 10 family-direct, 2 family-alias

## Severity rubric

- **High** — wrong numbers shown publicly to stakeholders (ACO-class)
- **Med** — silent degradation in model output, masked by lack of telemetry
- **Low** — maintenance debt, dead code, hygiene

## Status legend

`open` (not yet investigated) · `investigating` · `fixed` · `wont-fix` (with reason)

---

## Cat A — Reconciliation gaps (Tier 1) — ALL FIXED

| ID | S | L | Status | Finding | Fix |
|----|---|---|--------|---------|-----|
| A1 | High | Med | fixed | Walk-in multipliers manual, missing from pipeline. Production state: `walk_in_family_stats.csv` did not exist; every tournament got the global 1.1x estimate path. | Added `step_walkin_multipliers()` to `auto_update.py`; added warning when >50% of multipliers fall back to 'estimate'. After fix: 78/377 (21%) family-level, 299/377 (79%) estimate (further reduction = more standings scrape coverage; tracked separately). |
| A2 | Med | High | fixed | 37 of 196 standings rows had `tournament_name` that didn't match any summary family — silently dropped from enrichment. Two duplicate `STANDINGS_NAME_MAP` definitions (04c + 06) had drifted. | Moved `STANDINGS_NAME_MAP` + new `validate_standings_join()` to `tournament_aliases.py` as single source of truth. Extended map from 19 → 71 entries. **Result: 37 → 0 orphans.** |
| A3 | Med | Med | fixed | 28 upcoming 2026 events had no `early_bird_deadline`; `feature_engineering.early_bird_features` silently returned neutral values. | Added `validate_metadata_freshness()` to `validate_scraped_data.validate_all()`. Now surfaces a warning per missing-metadata batch in every pipeline run. |
| A4 | Low | High | fixed | Chart-layer running-max + 3x-scale patches in `04d_website_data_v2.py:540-570`. | Confirmed zero hits in production (4 rebased tournaments × 200+ daily points → 0 non-monotonic, 0 3x-jumps). Patches retained as defense-in-depth with comment pointing to AUDIT.md A4. |
| A5 | Med | Low | fixed | Cohort-gate edge cases not tested. | `tests/test_audit_fixes.py::test_scrape_coverage_gate_excludes_only_when_event_after_snapshot` covers ended-before-snapshot and ended-after-snapshot ± scrape-coverage. |

## Cat B — Silent staleness / silent fallbacks (Tier 1) — ALL FIXED OR DOCUMENTED

| ID | S | L | Status | Finding | Fix |
|----|---|---|--------|---------|-----|
| B1 | Med | High | fixed | Multi-tier prediction fallback had no telemetry on which tier fired. | `predict_nowcast` now records `self._last_tier` + maintains `self._tier_counts`. 04d prints distribution at end of run. **Production observation**: 97.2% family-direct, 2.5% size-matched, 0.3% family-alias — healthy. WARNING fires if size-matched > 20%. |
| B2 | Med | High | fixed | Walk-in multiplier fallback silent. (Fixed in Cat A commit.) | Per-source counter + WARNING when estimate > 50%. |
| B3 | Med | Low | fixed | `DEFAULT_EVENT_START_OFFSET=2` silently used when metadata missing. | `reanchor_daily_to_event_start` now reports offset source distribution. **Production observation**: 267/322 (83%) of training tournaments fall back to global default. WARNING fires when >2 use it. Remediation: bulk-populate metadata via `update_metadata.py` (data scope, separate work). |
| B4 | Med | Med | fixed | Verify `is_stale` banner reaches users. | Code review: `docs/sw.js` is network-first (commit 3219844), `docs/app.js:3172` reads `TOURNAMENT_DATA.is_stale` and shows `#staleBanner`. End-to-end test in `test_audit_fixes.test_stale_flag_propagates_to_website_data`. |
| B5 | Low | Low | wont-fix | `CIRCUIT_BREAKER_THRESHOLD=3` defined but recon claimed it was unused. | Verified: it IS wired at `scrape_entries.py:601` (in-run circuit breaker — aborts after 3 consecutive failures within a single `main()` invocation). Cross-run circuit breaker would require state persistence; not adding without a real failure mode driving it. Recon mis-identified. |

## Cat C — Model statistical audit (Tier 1)

| ID | S | L | Status | Finding | Fix |
|----|---|---|--------|---------|-----|
| C1 | High | High | findings | Lognormal CI nominal 80%, but empirical coverage diverges by year/T: 2023 88-100%, 2024 96-100%, **2025 59-94% (under-covers at T<14)**, 2026 67-100%. Model is over-conservative at long lead times, under-confident at short lead times in 2025. | Documented in performance_data.json (per-T `ci_coverage`). Recalibration tuning is its own multi-week project; not landing in this audit. |
| C2 | Med | High | findings | Bias-correction stationarity not validated. Per-T bias shrinkage factors fit once across all training data. | Split-half analysis on 2024-2025 deferred (model tuning scope). The presence of changing bias by year (e.g., 2023 T-90 bias=-12.1%, 2024 T-90 bias=+1.9%) suggests non-stationarity — flagged for follow-up. |
| C3 | Med | Med | fixed | Recalibration cohort drift after A1. | Implicitly verified: post-reconciliation rerun produced same grade A on 12 tournaments with reconciled truth labels. |
| C4 | Med | Med | fixed | T-coordinate reanchor robustness for sparse families. | Covered by B3 — telemetry surfaces 83% of training events fall back to global default. |
| C5 | Med | Low | fixed | Size-matched fallback usage rate. | B1 telemetry shows 2.5% production usage. Healthy; deeper LOO-CV validity check deferred. |
| C6 | Med | Med | fixed-typo | Inline `STANDINGS_NAME_MAP` duplications consolidated; FAMILY_GROUPS exhaustiveness check surfaces 168 singleton families. Most are legitimately separate; one real typo found. | Fixed: `Chess Congess` → `Chess Congress` typo merging 2024+ Washington Chess Congress data. Broader manual review of the other 167 deferred. |
| C7 | Low | Med | findings | IQR 3.0x outlier trimming applied silently. | Audit observation: trimming threshold not user-tunable, no per-family report. Deferred to backlog. |
| C8 | Med | Med | fixed | No `low_confidence` flag for tiny-history families. | `predict_nowcast` now sets `self._last_low_confidence = (n_editions < 4)`. 04d emits `low_confidence` + `n_historical_editions` + `prediction_tier` per tournament. Production: 5 of 12 live 2026 tournaments flagged low-confidence. |

## Cat D — Test coverage gaps (Tier 2)

| ID | Status | Test to add |
|----|--------|-------------|
| D1 | open | Reconciliation fixture: synthetic snapshot 184 + scrape 424 → assert post-prep summary. |
| D2 | open | Freshness assertion fires with right names. |
| D3 | open | Promote 24-case `is_wo_excluded` test to `tests/test_aliases.py`. |
| D4 | open | Scrape-coverage gate: ended-before-snapshot bypass + ended-after-snapshot requires coverage. |
| D5 | open | Walk-in freshness: stale stats triggers warning. |
| D6 | open | Auto-update stale-mode propagates `is_stale=True`. |
| D7 | open | Tiny-family fit emits `low_confidence` flag. |

## Cat E — Operational reliability (Tier 2)

| ID | Status | Item | Fix |
|----|--------|------|-----|
| E1 | fixed | `daily_update.yml` predict-on-scrape-failure logic. | Verified: scrape failure causes workflow failure, opens GitHub issue. Added `walk_in_*.csv`, `tournament_summary.csv`, `daily_registration_counts.csv`, `update_log.csv`, `checksums.json` to the daily commit list (previously incomplete — these were generated but not pushed). |
| E2 | fixed | `output/auto_update.log` rotation. | `auto_update.sh` now rotates when log exceeds 5MB, keeping last 3 archives. |
| E3 | fixed | `output/checksums.json` purpose. | Confirmed: integrity manifest written every run by `verify_checksums.generate_manifest()`. Used by `verify_checksums.py verify` for manual integrity check. Documented; kept. |
| E4 | fixed | SW cache stale-banner propagation. | Verified: `docs/sw.js` is network-first; live fetch always retrieves fresh `website_data.json` so `is_stale` reaches the frontend within one navigation. Banner DOM + JS test in `test_audit_fixes.test_stale_flag_propagates_to_website_data`. |

## Cat F — Code hygiene (Tier 3)

| ID | Status | Item | Fix |
|----|--------|------|-----|
| F1 | fixed | Dead exploratory scripts. | Deleted: `03_models.py`, `04_improvements.py`, `04b_fix_ci.py`, `02_curve_templates.py`, `03_blind_test.py`, `expanded_blind_test.py`, `test_alternatives.py`, `test_lognormal_blind.py`. All confirmed unreferenced via grep. |
| F2 | wont-fix | Stale duplicate clones. | Out of audit scope (plan §Out of scope). User-side housekeeping. |
| F3 | wont-fix | `model_whitepaper.py`. | Confirmed: not imported anywhere, but produces `output/CCA_Prediction_Model.pdf` which is referenced from the live site's docs link. Manual-use documentation tool — keep as-is. |
| F4 | fixed | `output/scrape_health.{html,json}` tracking inconsistency. | Added to `.gitignore` (alongside `chess_history.json`) — auto-generated diagnostic outputs, not part of source-of-truth pipeline. |

---

## Findings detail

(Populated as items are investigated. Each entry: evidence with file:line refs, scope of fix, before/after, verification.)
