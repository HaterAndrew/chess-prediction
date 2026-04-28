# Comprehensive Audit — chess_prediction

Started: 2026-04-28
Scope: `/home/dale/chess_prediction` only (stale duplicate clones at `~/chess-prediction`, `~/Desktop/chess-entry-predictor` get a one-line note in F2).
Trigger: stakeholder caught ACO 2026 displaying `final=184` (real: 424). Root cause shipped in commit `c5c516d` — this audit hunts the rest of the same defect class plus other Tier-1 risks.

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

| ID | S | L | Status | Finding |
|----|---|---|--------|---------|
| C1 | High | High | open | Lognormal CI empirical coverage vs claimed (80%/95%) on 2024–2025 backtest. |
| C2 | Med | High | open | Bias-correction stationarity. Split 2024–2025; fit on H1, evaluate on H2. |
| C3 | Med | Med | open | Recalibration cohort drift after upstream reconciliation. |
| C4 | Med | Med | open | T-coordinate reanchor robustness for families with <3 completed events. |
| C5 | Med | Low | open | Size-matched fallback validity via leave-one-family-out CV. |
| C6 | Med | Med | open | `FAMILY_GROUPS` exhaustiveness vs all unique family names in summary. |
| C7 | Low | Med | open | Per-T outlier trimming (IQR 3.0x) — quantify points trimmed per family. |
| C8 | Med | Med | open | No `low_confidence` flag for families with `n < 4` historical points. |

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

| ID | Status | Item |
|----|--------|------|
| E1 | open | `daily_update.yml` predict-on-scrape-failure intentionality + failure issue creation. |
| E2 | open | `output/auto_update.log` rotation. |
| E3 | open | `output/checksums.json` use case — keep + document, or delete. |
| E4 | open | Service worker `is_stale` propagation under aggressive caches. |

## Cat F — Code hygiene (Tier 3)

| ID | Status | Item |
|----|--------|------|
| F1 | open | Delete dead exploratory scripts (03_models, 04_improvements, 04b_fix_ci, 02_curve_templates, 03_blind_test, expanded_blind_test). |
| F2 | open | One-line "stale clone" note in `~/chess-prediction` + `~/Desktop/chess-entry-predictor`. |
| F3 | open | `model_whitepaper.py` — referenced anywhere? Delete or relocate to `docs/`. |
| F4 | open | gitignore `output/scrape_health.{html,json}` (or commit, not both). |

---

## Findings detail

(Populated as items are investigated. Each entry: evidence with file:line refs, scope of fix, before/after, verification.)
