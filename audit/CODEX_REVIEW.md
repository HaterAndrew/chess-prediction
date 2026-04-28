# Codex Review Brief — Full audit + reconciliation fixes (2026-04-28)

**Repo:** `github.com/HaterAndrew/chess-prediction`
**Branch:** `main`
**Commits to review (in order):**

| Commit | Title | Scope |
|---|---|---|
| [c5c516d](https://github.com/HaterAndrew/chess-prediction/commit/c5c516d) | Reconcile snapshot vs scrape pipeline-wide | Original ACO 184→424 fix; six structural fixes + freshness assertion |
| [74499c3](https://github.com/HaterAndrew/chess-prediction/commit/74499c3) | Regenerate outputs after reconciliation | Output-only |
| [a3b33eb](https://github.com/HaterAndrew/chess-prediction/commit/a3b33eb) | Audit Cat A — reconciliation gaps | 5 items: walk-in pipeline, standings join, metadata freshness, chart patch redundancy, scrape-coverage gate |
| [d0969fa](https://github.com/HaterAndrew/chess-prediction/commit/d0969fa) | Audit Cat B — silent staleness/fallbacks | 5 items: prediction tier telemetry, walk-in source, event-start offset, stale banner, circuit breaker |
| [3f3e719](https://github.com/HaterAndrew/chess-prediction/commit/3f3e719) | Audit Cat C — model statistical audit (initial) | 5 items: cohort drift, T-coordinate robustness, size-matched fallback, alias exhaustiveness, low_confidence flag |
| [97fab81](https://github.com/HaterAndrew/chess-prediction/commit/97fab81) | Audit Cat E+F — ops + hygiene | CI commit-list, log rotation, checksums, SW cache, dead-file cleanup, gitignore |
| [d64c7ce](https://github.com/HaterAndrew/chess-prediction/commit/d64c7ce) | AUDIT.md final status | Doc-only |
| [41968d1](https://github.com/HaterAndrew/chess-prediction/commit/41968d1) | Audit Cat C deferred — C1/C2/C7 | CI calibration math, bias stationarity probe, IQR trim accounting |
| [132c6ac](https://github.com/HaterAndrew/chess-prediction/commit/132c6ac) | This review brief | Doc-only |

Net changes today: ~33 audit findings tracked, **30 fixed**, 3 wont-fix (with rationale). 82 tests passing (29 new in `tests/test_audit_fixes.py`).

This brief is meant as a starting point for adversarial review across the **full scope**. Goal: confirm the math, catch logical bugs, and challenge any assumption made. The original audit charter is in [audit/AUDIT.md](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/audit/AUDIT.md).

---

## Trigger

Stakeholder asked why "Atlantic City Open final = 184" appeared on the model performance tab when the actual final was 424. Investigation showed the model was being graded against a stale 2026-03-22 snapshot of registration data that had never reconciled with the live daily scraper. The same defect class (two unreconciled sources / silent staleness / spot-fix-not-class-fix) had been point-fixed at five other layers in the prior 30 days. The full body of work below addresses the immediate bug AND the structural failure mode it represented.

---

## Section 1 — Snapshot/scrape reconciliation (commit c5c516d)

### What was wrong

`tournament_summary.csv` was built from `~/Downloads/all_registrations.csv` (manual snapshot, last touched 2026-03-22). For tournaments where registrations grew past that date, `final_count` froze at the snapshot value while `daily_scrape.csv` (auto-polled) tracked the live count. The performance grader compared predictions against the frozen value — fictitious accuracy.

12 of 32 tracked 2026 tournaments affected. ACO: 184→424 (+130%). Chicago Open: 179→333 (+86%).

### What changed

**1. `01_data_prep.py` — reconciliation at ingest** ([01_data_prep.py:172-265](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/01_data_prep.py#L172-L265))
- After building `summary` from the snapshot, merge against `daily_scrape.csv` peak; take `max()` of snapshot final_count and scrape peak.
- For tournaments where scrape extends past snapshot's `last_reg`, rebase `last_reg` to the latest scrape date.
- For rebased tournaments, inject scrape-derived rows into `daily_registration_counts.csv` covering the gap, then take running cummax across archive+scrape so the curve is monotonic.

**2. `04e_performance_data.py` — freshness assertion** ([04e_performance_data.py:172-197](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04e_performance_data.py#L172-L197))
- Defense-in-depth: refuses to run grading if `daily_scrape.csv` shows a higher `entry_count` than `summary.final_count` for any tournament. Tolerance of 5 absorbs minor timing differences.

**3. `auto_update.py` — pipeline wired** ([auto_update.py:92-130](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/auto_update.py#L92-L130))
- New `step_data_prep()` runs `01_data_prep.py` after scrape, before model regen.
- Tolerates missing `~/Downloads/all_registrations.csv` (skips with warning rather than aborting); the freshness assertion is the safety net.

### Things to check
- `01_data_prep.py:230-265` (curve extension): the running cummax merge takes scrape rows for T values <= old archive's max-T. If old archive ended at T=15 and scrape starts at T=13, are T=14/13/12... archive points overshadowed correctly? Walk through with synthetic data.
- The reconciliation is a one-way bump (scrape ≥ snapshot wins). Could there ever be a legitimate case where snapshot > scrape (e.g., scrape misses a withdrawal cleanup)? In current data, no. But the assumption deserves a sanity check.
- The freshness assertion's tolerance=5 — is that the right small-number? If a tournament truly closed at 100 and scrape's max was 102, we don't want to abort on a 2-row difference. But if it was 100 vs 110, we should.

---

## Section 2 — Cat A reconciliation gaps (commit a3b33eb)

### A1 — Walk-in multipliers wired into pipeline

**File:** [auto_update.py:111-130](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/auto_update.py#L111-L130) (new `step_walkin_multipliers()`)

**State before:** `output/walk_in_family_stats.csv` did not exist in production. `04c_final_model.load_walkin_multipliers()` returned `{}`, every tournament got the global 1.1× estimate path. The whole walk-in system was a no-op.

**State after:** `06_walk_in_multipliers.py` runs every pipeline cycle. Production: 78/377 (21%) tournaments now get family-specific multipliers. Loud WARNING fires when estimate-fallback ratio exceeds 50%.

**Things to check:** the hard `min(median_ratio, 1.1)` cap inside `apply_walkin_multiplier` ([04c_final_model.py:1788](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04c_final_model.py#L1788)) means even when family stats say 1.65, the applied multiplier is 1.1. Is that cap deliberate (conservative hedge against over-prediction) or a bug? Commit history (`cd0f75f`, `ca7350a`) suggests deliberate.

### A2 — Standings join validation (37 → 0 orphans)

**Files:** [tournament_aliases.py:90-167](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/tournament_aliases.py#L90-L167), [04c_final_model.py:401-419](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04c_final_model.py#L401-L419), [06_walk_in_multipliers.py:34-37](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/06_walk_in_multipliers.py#L34-L37)

**State before:** Two duplicate `STANDINGS_NAME_MAP` definitions (one inline in 04c, one inline in 06) had drifted. 37 of 196 standings rows had names that didn't match any summary family — silently dropped from `build_enrichment_lookup`.

**State after:** Single source of truth in `tournament_aliases.STANDINGS_NAME_MAP` (extended from 19 → 71 entries). Both 04c and 06 import from it. New `validate_standings_join()` prints orphans loudly. Production: 0 orphans.

**Things to check:** the extended map includes some heuristic guesses (e.g., `'Atlantic'` → `'Atlantic Open'`, `'Boston'` → `'Boston Chess Congress'`). Are any of these wrong? The fixture-bound test (`test_standings_name_map_zero_orphans`) confirms current data joins cleanly, but doesn't validate semantic correctness.

### A3 — Metadata freshness check

**File:** [validate_scraped_data.py:269-303](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/validate_scraped_data.py#L269-L303)

`validate_metadata_freshness()` flags upcoming events with no `early_bird_deadline` set. Production: 28 upcoming 2026 events flagged. `feature_engineering.early_bird_features` returns neutral values for these — degraded model signal, now visible.

### A4 — Chart-layer patches downgraded to defense-in-depth

**File:** [04d_website_data_v2.py:540-570](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04d_website_data_v2.py#L540-L570)

The 5 sequential 2026-04-06 chart fixes (running-max, scale-fudge, drop-archive-after-handoff) were patches over the same underlying defect now fixed upstream. Confirmed zero hits in production after upstream fix; kept as safety net (run when `step_data_prep` is skipped) with comment pointing to AUDIT.md A4.

### A5 — Scrape-coverage gate edge cases

**File:** [04e_performance_data.py:236-281](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04e_performance_data.py#L236-L281), [tests/test_audit_fixes.py:88-104](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/tests/test_audit_fixes.py#L88-L104)

Cohort gate: include 2026 tournaments only if (a) event ended before snapshot date OR (b) has scrape coverage. Test covers both branches.

**Things to check:** snapshot date is inferred as `max(last_reg)` across summary. After reconciliation rebases `last_reg` for some tournaments, that max can equal "today" rather than the actual snapshot export date. Does this break the gate? Walk through with a stale-snapshot scenario.

---

## Section 3 — Cat B silent fallbacks (commit d0969fa)

### B1 — Prediction tier telemetry

**File:** [04c_final_model.py:711-725, 765-790](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04c_final_model.py#L711-L790), [04d_website_data_v2.py:920-936](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04d_website_data_v2.py#L920-L936)

`predict_nowcast` records `self._last_tier` and increments `self._tier_counts[tier]` on each call. Tiers: `family-direct`, `family-alias`, `size-matched`, `guard-no-data`, `guard-event-started`, `guard-no-ratios`. 04d prints distribution at end of run; WARNING when size-matched fallback >20%. Production: 97.2% direct, 2.5% size-matched, 0.3% alias.

### B2 — Walk-in source telemetry

**File:** [04d_website_data_v2.py:870-895](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04d_website_data_v2.py#L870-L895)

Per-source counter `{family, type, estimate, none}`. WARNING when estimate >50%. Production: 265 family / 112 estimate (was 0/377 before A1).

### B3 — Event-start offset visibility

**File:** [04c_final_model.py:92-145](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04c_final_model.py#L92-L145)

`reanchor_daily_to_event_start()` now reports offset source distribution. **Major surprise:** 267/322 (83%) of training tournaments fall back to `DEFAULT_EVENT_START_OFFSET=2` because historical metadata is sparse. WARNING fires when >2 use it. Remediation = bulk-populate metadata; data-scope work, separate.

### B4 — Stale banner

**Files:** [docs/sw.js](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/docs/sw.js), [docs/app.js:3170-3182](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/docs/app.js#L3170-L3182), [tests/test_audit_fixes.py:160-186](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/tests/test_audit_fixes.py#L160-L186) (`test_stale_flag_propagates_to_website_data`)

Code-review verified network-first SW + correct DOM wiring. End-to-end test added.

### B5 — Circuit breaker

**Wont-fix.** Recon claimed `CIRCUIT_BREAKER_THRESHOLD=3` was unused; verified it IS wired at [scrape_entries.py:601](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/scrape_entries.py#L601) (in-run). Cross-run version not justified without a real failure mode.

### Things to check across Cat B
- All Cat B telemetry adds module-level state. Are any `_tier_counts` leaks across model instances? Each fit resets `_tier_counts` lazily on first call — could that double-count if two models are instantiated in the same process?

---

## Section 4 — Cat C original (commit 3f3e719)

### C3 / C4 / C5 — implicit verification

C3 (recalibration cohort drift after reconciliation), C4 (T-coordinate reanchor robustness), C5 (size-matched fallback usage rate) were implicitly verified by post-fix reruns + B1/B3 telemetry. Documented; no new code beyond what B1/B3 added.

### C6 — alias exhaustiveness + `'Chess Congess'` typo

**File:** [01_data_prep.py:54-58](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/01_data_prep.py#L54-L58)

168 singleton families exist outside `FAMILY_GROUPS`. One real typo found: `'Washington Chess Congess'` (missing 'r'). Now normalized to `'Washington Chess Congress'`. Other 167 deferred (mostly legitimately distinct events).

### C8 — `low_confidence` flag

**File:** [04c_final_model.py:716-722](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04c_final_model.py#L716-L722), [04d_website_data_v2.py:610-617, 633-635](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04d_website_data_v2.py#L610-L635)

`predict_nowcast` sets `self._last_low_confidence = (n_editions < 4)`. 04d emits `low_confidence`, `n_historical_editions`, and `prediction_tier` per tournament. Production: 5 of 12 live 2026 events flagged (Bradley, Hartford, Pacific Coast, Pittsburgh, Cleveland).

### Things to check
- The `n < 4` threshold for `low_confidence`. Is 4 the right cutoff? Lognormal CI fits with 2 data points but they're meaningless; with 4 data points the t-distribution starts to behave. The choice is principled but could be 5 or 6 depending on how strict you want.

---

## Section 5 — Cat C deferred — C1, C2, C7 (commit 41968d1)

### C1 — Continuous CI calibration

**File:** [04c_final_model.py:1152-1290](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04c_final_model.py#L1152-L1290)

Replaced 5-bucket step function for `ci_adj` with continuous derivation:

```python
empirical_q = np.percentile(
    [|log(actual_i) - log(predicted_i)| / log_halfwidth_i for i in cohort],
    target_coverage * 100
)
ci_adj = clamp(empirical_q, 0.5, 1.8)
```

**Math claim:** `norm_residual = |log_residual| / log_halfwidth` is in units of "half-width". The 80th percentile of this in the cohort IS the multiplicative scale needed to make 80% of residuals fall inside the rescaled CI.

**Result:** cumulative T-14 coverage hits exactly 80.0% (was 90% over-cover).

### C2 — Bias stationarity probe

**File:** [04c_final_model.py:1244-1271](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04c_final_model.py#L1244-L1271)

Same `recalibrate()` function. When n>=6 records at a given T, sort cohort by `last_reg`, split at median index, compare mean bias across halves, WARNING when |delta| > 5pp. Production: T=3 fired with old=-2.8%, new=+3.0% (Δ=5.8pp).

### C7 — Per-family trim accounting

**Files:** [04c_final_model.py:238-310](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04c_final_model.py#L238-L310) (`_TRIM_STATS`, `trim_outliers`, `reset_trim_stats`, `report_trim_stats`), [04c_final_model.py:312-330](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04c_final_model.py#L312-L330) (`lognormal_ci` accepts `label=`), per-family call sites at [858, 875](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/04c_final_model.py#L858).

Module-level `_TRIM_STATS` counters with per-label tally. End-of-fit log + WARNING at >8% trim rate. Production: 5.48% trimmed.

### Things to check across Cat C deferred
1. **Math in C1**: under what residual distribution is `quantile(|log_residual|/log_halfwidth, 0.80)` exactly the right scale? It assumes lognormal CI's half-width scales linearly with the scale parameter — true for lognormal in log-space. If residuals are NOT lognormal in log-space (heavy tails, skew), what bias does this introduce at n~10-40 per T-band?
2. **C2 split**: "split at median index after sort by `last_reg`" — degenerate cases? All records same date, missing `last_reg`? Better to use Mann-Whitney with p-value gate?
3. **C7 double-counting**: walk the call graph. `trim_outliers` is called inside `lognormal_ci`. `lognormal_ci` is called from training (LOO calibration loop with binary search), prediction (`predict_nowcast`), and blind-test code. Could the same training point flow through `trim_outliers` multiple times in one fit?
4. **Side effect of C1 fix**: 2025 backtest grade dropped from B+ to C+ because the old step function's 0.90 cap was hiding mis-calibration by force-narrowing CIs. Is the C+ grade honest or a regression?

---

## Section 6 — Cat E + F (commit 97fab81)

Operational + hygiene cleanup. Lower stakes; review for completeness rather than depth.

- [.github/workflows/daily_update.yml:50](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/.github/workflows/daily_update.yml#L50): extended commit list to include `walk_in_*.csv`, `tournament_summary.csv`, `daily_registration_counts.csv`, `update_log.csv`, `checksums.json`. These were generated daily but never pushed — fresh clones came up missing.
- [auto_update.sh:7-15](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/auto_update.sh#L7-L15): log rotation when `output/auto_update.log` exceeds 5MB.
- F1: deleted 8 confirmed-unused files (`03_models.py`, `04_improvements.py`, `04b_fix_ci.py`, `02_curve_templates.py`, `03_blind_test.py`, `expanded_blind_test.py`, `test_alternatives.py`, `test_lognormal_blind.py`).
- F4: gitignored `output/scrape_health.{html,json}`.

---

## Tests

[tests/test_audit_fixes.py](https://github.com/HaterAndrew/chess-prediction/blob/132c6ac/tests/test_audit_fixes.py) — 37 tests covering every fix in this audit.

Total suite: **82 passing** (45 in `test_pipeline_integration.py` + 37 in `test_audit_fixes.py`).

**Tests that should exist but don't:**
- End-to-end coverage check on synthetic residuals for C1 (construct known residual stream → run recalibrate → verify resulting empirical coverage matches target).
- C7 trim accounting under nested calls (does count remain accurate when `lognormal_ci` calls `trim_outliers` from inside a binary-search loop?).
- Property-based test for the reconciliation logic (snapshot N + scrape M, where M > N → output should be M).

---

## Verification commands

```bash
git clone https://github.com/HaterAndrew/chess-prediction.git
cd chess-prediction
git checkout 132c6ac

pip install pandas numpy scipy scikit-learn pytest

# Tests
pytest tests/ -v               # 82 should pass

# Full pipeline
python3 auto_update.py --skip-scrape

# Inspect diagnostics
cat audit/AUDIT.md             # 30 of 33 closed
python3 -c "import json; d = json.load(open('output/performance_data.json')); print('cumulative T-14 cov:', [a for a in d['cumulative']['aggregate'] if a['T']==14])"
# expect: cov around 80% (the headline C1 claim)
```

---

## What I want codex to do

1. Confirm the math in C1 (the headline claim).
2. Walk the C7 call graph and rule out double-counting.
3. Stress-test the reconciliation logic in `01_data_prep.py:172-265` with edge cases — overlapping T values between archive and scrape, scrape data older than snapshot, `last_reg` rebased to today, etc.
4. Check the alias map extensions in A2 — heuristic guesses like `'Atlantic'` → `'Atlantic Open'` could be wrong (could be `'Atlantic City Open'`).
5. Look for silent assumptions in B1's `_tier_counts` (model-instance vs module-level concerns).
6. Spot-check anything in the audit that looks rushed.

Three buckets back:
- **BLOCKERS**: math errors, silent bugs, tests that don't actually test what they claim
- **CONCERNS**: judgment calls that are defensible but worth questioning (clamp ranges, thresholds, split methods, alias guesses)
- **NITS**: style, naming, missing docstrings

Be direct. The goal is adversarial review, not validation. If something is fine, say so explicitly.
