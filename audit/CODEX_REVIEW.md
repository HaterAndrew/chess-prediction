# Codex Review Brief — C1 / C2 / C7 follow-up

**Repo:** `github.com/HaterAndrew/chess-prediction`
**Commit:** `41968d1` (on `main`)
**Date:** 2026-04-28
**Scope:** Three previously-deferred Cat C audit items (model statistical assumptions). All three landed in this single commit on top of the prior audit work (`d64c7ce`, `97fab81`, `3f3e719`, `d0969fa`, `a3b33eb`).

This brief is meant as a starting point for adversarial review. Goal: confirm the math, catch logical bugs, and challenge any assumption I've made.

---

## What was wrong before

The chess-prediction model claims an **80% confidence interval** on every prediction. Until this commit, three things were left unaddressed by the audit:

1. **C1 — CI calibration drift.** The model's `recalibrate()` adjusted CI width via a 5-bucket step function (`1.15 / 1.08 / 1.0 / 0.95 / 0.90`). Empirical coverage was free to land anywhere in `[0%, 100%]` — observed: 2024 96-100% (over-cover), 2025 59-94% (under-cover at short lead). The headline "CI coverage" displayed publicly was untethered from the model's nominal claim.
2. **C2 — Bias correction stationarity unverified.** Per-T bias factors were fit once over the entire training cohort. No check that bias was consistent across time. Year-over-year evidence of drift (2023 T-90 bias=-12.1%, 2024 T-90 bias=+1.9%) suggested it wasn't stationary.
3. **C7 — Silent outlier trimming.** `trim_outliers()` (IQR 3.0×) ran inside every CI computation, dropped ~5% of training points, and never reported per-family counts. No way to detect "this family lost half its data to trimming" before it became a downstream bug.

---

## What changed (all in `04c_final_model.py`)

### C1 — Continuous CI calibration

**File:** [04c_final_model.py:1152-1290](https://github.com/HaterAndrew/chess-prediction/blob/41968d1/04c_final_model.py#L1152-L1290)

Replaced the step function with a continuous derivation:

```python
# For each completed (tournament, T) pair we have:
#   actual                 = ground-truth final count
#   point, lo, hi          = raw model prediction at that T (no recalibration applied)
#   log_halfw              = (log(hi) - log(lo)) / 2          # current CI half-width in log space
#   log_residual           = |log(actual) - log(point)|       # how far off, in log space
#   norm_residual          = log_residual / log_halfw         # >1 means CI too narrow

# Aggregating across the calibration cohort:
empirical_q = np.percentile(norm_residuals, target_coverage * 100)   # default target = 80%
ci_adj = clamp(empirical_q, ci_min_scale=0.5, ci_max_scale=1.8)
```

**Math claim being made:** if the model's current 80% lognormal CI's half-width is `log_halfw` and the empirical 80th percentile of |log_residual| is `q`, then scaling the half-width by `q / 1.0 = q` makes 80% of residuals fall within the new half-width. The unit here is "half-width" — `norm_residual = 1.0` means "this residual exactly fills the CI", so the 80th percentile of `norm_residual` IS the multiplicative scale needed.

**Things to check:**
- Does this hold under lognormal residuals? My intuition says yes (linear scaling of the log-space half-width = the empirical quantile in the same units), but I want a second pair of eyes on the dimensional analysis.
- The `target_coverage` defaults to 0.80. Is the function correct if a caller passes 0.95? The code uses `target_coverage * 100` for percentile, which gives 95 for target=0.95 — ✓.
- The clamp range `[0.5, 1.8]` is judgment. Below 0.5 = "model is so over-covering we'd rather force-narrow", above 1.8 = "we don't trust the empirical signal that much". Reasonable bounds?
- Need at least 3 records per T to compute a percentile. Below that the loop `continue`s — silently reverting to no recalibration at that T. Is `<3 → skip` the right behavior? An alternative: borrow the global ci_scale from the binary-search LOO calibration done at fit time.

**Result observed:** cumulative T-14 coverage went from 90% (over-cover) → exactly 80%. 2025 individual-year coverage stays low (56%) — see C2 below for why.

### C2 — Bias stationarity probe

**File:** [04c_final_model.py:1244-1271](https://github.com/HaterAndrew/chess-prediction/blob/41968d1/04c_final_model.py#L1244-L1271)

Same `recalibrate()` function, additional logic. When the cohort at a given T has >=6 records, sort chronologically (by `last_reg`), split into older half / newer half, compute mean bias on each half, report.

```python
if len(records) >= 6:
    mid = len(records) // 2
    old_half = err_arr[:mid]
    new_half = err_arr[mid:]
    stationarity = {
        'old_bias_pct': round(float(np.mean(old_half)) * 100, 1),
        'new_bias_pct': round(float(np.mean(new_half)) * 100, 1),
        'delta_pct': round((np.mean(new_half) - np.mean(old_half)) * 100, 1),
    }
```

A WARNING fires when `|delta_pct| > 5.0`.

**Things to check:**
- "Older / newer half" is by `last_reg`, not by event start date. For tournaments where `last_reg` was rebased to scrape's last date (per [c5c516d](https://github.com/HaterAndrew/chess-prediction/commit/c5c516d)), this might not match temporal intent. Probably OK — what we want is "data we observed earlier" vs "data we observed later" and `last_reg` tracks that.
- The 5.0pp threshold is judgment. Probably right — anything below 5pp is within sampling noise for n~20-40.
- Output is logged but not fed back into model behavior (no automatic cohort-restriction on detection of non-stationarity). Was deliberate: I want the operator to decide whether to switch cohorts; non-stationarity doesn't always mean "discard older data".
- Is splitting at `len(records) // 2` the best split point? Alternatives: split at the median date, or quartiles. Even-N split keeps the test simple but ignores actual time gaps.

**Production observation:** T=3 fired with old=-2.8%, new=+3.0% (Δ=5.8pp) — real non-stationarity at short lead times, evidence the probe is detecting a real effect.

### C7 — Per-family trim accounting

**Files:** [04c_final_model.py:238-310](https://github.com/HaterAndrew/chess-prediction/blob/41968d1/04c_final_model.py#L238-L310), [04c_final_model.py:312-330](https://github.com/HaterAndrew/chess-prediction/blob/41968d1/04c_final_model.py#L312-L330) (lognormal_ci), [04c_final_model.py:858-859, 875](https://github.com/HaterAndrew/chess-prediction/blob/41968d1/04c_final_model.py#L858-L875) (predict_nowcast call sites)

Module-level counters:
```python
_TRIM_STATS = {'total_in': 0, 'total_out': 0, 'by_label': defaultdict(lambda: [0, 0])}

def trim_outliers(values, iqr_factor=3.0, label=None):
    # ... existing IQR logic ...
    if label is not None:
        _TRIM_STATS['by_label'][label][0] += len(values)
        _TRIM_STATS['by_label'][label][1] += len(result)
    _TRIM_STATS['total_in'] += len(values)
    _TRIM_STATS['total_out'] += len(result)
    return result
```

`reset_trim_stats()` is called at the start of every `fit()`. `report_trim_stats()` returns aggregate + top-5 offenders. End of fit prints:

```
IQR outlier trim: 5446/99396 points trimmed (5.48%)
Top families by trim rate:
  <family> 4/8 (50.0%)
  ...
```

WARNING at >8% (set above current production rate of ~5.5%).

**Things to check:**
- Mutable module-level state. Tests must `reset_trim_stats()` to be deterministic (the test does). Is this the right mechanism, or should counters live on the model instance? I went module-level because `lognormal_ci` is a module-level function and threading state through every caller would be more invasive.
- The `label=` arg is opt-in — call sites that don't pass it still increment `total_in/total_out` but not `by_label`. Currently only `predict_nowcast`'s per-family lognormal_ci calls pass label. Other call sites (the binary-search LOO calibration, blind-test) don't. This is intentional: "by family" only makes sense at production-prediction sites; calibration runs are aggregate. Worth challenging.
- Threshold of 8% for the warning is judgment based on current healthy-state of 5.48%. If the underlying distribution is actually heavy-tailed-by-design (lognormal ratios in linear space WILL produce extreme outliers), maybe 5% is fine and the warning shouldn't fire ever. Open question.
- Does counting in `trim_outliers` double-count when called in tight loops? Each call adds (n_in, n_out) once per call. If the same data flows through trim_outliers twice (e.g., during a binary search), it counts twice. Need to verify whether that happens in practice; if so the percentages overstate.

---

## Tests added

[tests/test_audit_fixes.py:160-227](https://github.com/HaterAndrew/chess-prediction/blob/41968d1/tests/test_audit_fixes.py#L160-L227)

- `test_recalibrate_targets_continuous_coverage` — `ci_adj` is a true float, not snap to legacy bucket; `target_coverage=80` is in the diagnostic dict.
- `test_recalibrate_emits_stationarity_check` — at >=6 records the diagnostic includes `'stationarity'` key.
- `test_trim_outliers_records_per_label_stats` — `_TRIM_STATS` accumulates per-label counts; `report_trim_stats()` produces sane structure.

Full suite: 82 pass.

---

## Pipeline output (verification)

Running `python3 auto_update.py --skip-scrape` on the fix produces:

- `IQR outlier trim: 54600/995880 points trimmed (5.48%)` — C7 visibility working
- `WARNING: T=3 bias non-stationary (old half: -2.8%, new half: 3.0%, Δ=5.8pp). Recent-cohort recalibration recommended.` — C2 detection working
- 04e per-year output: 2024 still over-covers, 2025 still under-covers, **2026 + cumulative** now hit nominal 80% target (cumulative: T-14 MAE 9.8%, CI coverage **80.0%**). C1 working at the level it claims.

---

## What I'm specifically asking codex to check

1. **The math in C1**: is `empirical_q = quantile(|log_residual| / log_halfw, 0.80)` correctly the multiplicative scale needed to make 80% of residuals fall inside the resulting CI? I'm 90% sure this is right, but it relies on the linearity of the lognormal CI's half-width with respect to the scale parameter. If residuals are NOT lognormal in log-space, this is biased.
2. **C2's split**: is "split at median index after sorting by `last_reg`" a defensible stationarity test? Alternative: Mann-Whitney on the two halves, with a p-value gate instead of a bare 5pp threshold.
3. **C7's double-counting risk**: walk through the call graph and confirm `trim_outliers` is called exactly once per training point per fit. If it's called multiple times in the calibration's binary search, the percentages reported overstate.
4. **Side effect of the C1 fix**: 2025 backtest grade dropped from B+ to C+ because the CI is now narrower (we removed the over-conservative 0.90 cap that was hiding mis-calibration). Is this honestly better, or did I just make the visible grade worse without improving the model? My read: the public CI was lying before; now it's not. C+ is the truth.
5. **Anything else**: any silent assumption I made, any edge case I missed, any test I forgot to write.

---

## Files changed (this commit)

| File | Lines changed | What |
|---|---|---|
| `04c_final_model.py` | +148 / -38 | C1 recalibrate rewrite, C2 stationarity probe, C7 trim accounting + reset/report functions |
| `04d_website_data_v2.py` | +3 / -1 | Read `coverage_before` from new diagnostic dict (was reading old `coverage` key) |
| `audit/AUDIT.md` | +12 / -6 | Status update: C1/C2/C7 marked fixed; 30/33 closed |
| `tests/test_audit_fixes.py` | +73 / -1 | 3 new tests (C1, C2, C7) |
| Output JSONs / index.html | regenerated | Reflects rerun pipeline |

Total: ~240 lines of source change, ~70 lines of test, plus regenerated outputs.

---

## How to run the review

```bash
# Clone fresh
git clone https://github.com/HaterAndrew/chess-prediction.git
cd chess-prediction
git checkout 41968d1

# Install deps
pip install pandas numpy scipy scikit-learn pytest

# Tests
pytest tests/test_audit_fixes.py::test_recalibrate_targets_continuous_coverage -v
pytest tests/test_audit_fixes.py::test_recalibrate_emits_stationarity_check -v
pytest tests/test_audit_fixes.py::test_trim_outliers_records_per_label_stats -v

# Full pipeline (skip-scrape so it doesn't hit the live CCA site)
python3 auto_update.py --skip-scrape

# Inspect output
cat audit/AUDIT.md          # all 33 findings + status
cat output/performance_data.json | python3 -m json.tool | head -50
```

The audit's prior commits (`a3b33eb` Cat A, `d0969fa` Cat B, `3f3e719` Cat C-original, `97fab81` Cat E+F) are also reachable from `main` and contribute the surrounding telemetry context this commit relies on.
