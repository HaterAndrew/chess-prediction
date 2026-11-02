# Chess Prediction Maintenance: November 2, 2026

The local candidate corrects registration charts for 24 tournament cards, validates all 11 dependency updates, and makes workflow changes run Python CI. All 412 cards retain their forecast values. All 1,086 walk-forward records retain all 26 column values. The candidate preserves the original sealed cohort.

The admin-count comparison covers all 30 overlapping 2026 editions. Eighteen match exactly. The remaining twelve expose withdrawals, deleted registrations, and snapshot differences. Two completed events each retain a one-entry historical difference. The evidence does not establish that every scraped count measures the same population as an admin export.

## Candidate and Validation

- Base revision: `0f1a42297c89815d538cfaf7a4beff8ba8550c62`.
- Branch: `maintenance/2026-11-02`.
- Model label: `n5v6`; forecast behavior remains unchanged.
- Accepted display-source hash: `e2b539beaa9c6f75`.
- Python 3.12.14 and Node 22.23.2 match the application runtime requirements.
- Final checks: 986 Python tests, 62 Worker tests, Ruff, actionlint, output checksums, and Wrangler deployment dry run pass.
- The clean final npm lock passes installation and audit. npm reports zero known vulnerabilities. pip-audit 2.10.1 reports zero across the 37 resolved Python packages.
- Independent code and security reviews have no open supported findings after the corrections and final checks.
- Python emits two pandas 3.1 deprecation notices in `recalibrate.py` and `scripts/perf_diff.py`. Neither fails a check.

Validation covers a local candidate. Production deployment and retirement of the old Worker remain separate release operations.

## Reliability and Chart Corrections

The previous World Open chart ended at 25 registrations. Its completed-event fallback also dated stale archive observations near July instead of their original November-to-March dates. The corrected chart starts on November 26, 2025 and reaches 1,066 on July 5, 2026.

The chart builder now reads the written aggregate curve separately from the model corpus. It dates archive observations from their recorded last registration, appends later observed scrape days, and stops both sources at the event end. It keeps tournament years and World Open sections separate. It does not interpolate missing observations or rescale earlier counts.

The chart correction changes 24 cards across completed 2026 editions. Forecast fitting, pickup inputs, point estimates, ranges, routes, tiers, counts, and shadow forecasts remain unchanged. The final data-health scan has zero critical, high, or medium findings and 26 information findings. Missing training history and fallback walk-in estimates remain visible.

Python CI now includes `.github/workflows/**` in its PR paths. A regression covers existing Python workflows and a future workflow path. The old filter failed the existing cases; a three-path control failed the future case. The final filter passes all cases.

The workflows retain their permissions and publishing conditions. They use verified setup-action SHAs, keep the existing Python and Node versions, and cancel superseded non-main runs. The shell summaries use quoted paths and grouped redirects. Worker CI also supports manual execution.

Chrome checks cover the local forecast, corrected World Open chart, fee disclosure, season view, and model view. The chart renders in the existing light and dark themes. The model view retains 11 sealed forecasts. The season view retains all nine 2027 cards. The console reports no errors during these checks.

The live application loaded November 2 data in Chrome. The browser client blocked the live `/health` URL; the deployed endpoint remains unverified. Local Worker tests and the deployment dry run passed.

## Forecast Accuracy

These figures use the current committed final labels. The count reconciliation below limits claims about their target population.

The walk-forward backtest reconstructs forecasts from prior data. The published record grades the forecasts visitors actually saw and includes older model versions. The latter shows weaker short-lead interval coverage. Its 23 finished events span 16 model versions, so that result alone does not identify a defect in the current frozen model.

| Lead Time | Walk-Forward n | Mean Absolute Error | Range Coverage | Published n | Mean Absolute Error | Range Coverage |
|---|---:|---:|---:|---:|---:|---:|
| T-90 | 105 | 11.50% | 75.2% | 17 | 18.79% | 70.6% |
| T-60 | 136 | 12.34% | 79.4% | 21 | 16.48% | 81.0% |
| T-42 | 140 | 12.07% | 78.6% | 21 | 17.09% | 71.4% |
| T-28 | 140 | 11.00% | 79.3% | 20 | 13.62% | 65.0% |
| T-14 | 140 | 8.35% | 82.9% | 21 | 11.04% | 66.7% |
| T-7 | 141 | 7.47% | 86.5% | 23 | 9.82% | 65.2% |
| T-3 | 142 | 8.48% | 84.5% | 23 | 12.03% | 60.9% |
| T-1 | 142 | 5.76% | 82.4% | 23 | 9.62% | 52.2% |

The published T-1 coverage is 52% with a 95% interval of 33%-71%. That mixed-era record under-covers the 80% target. The sealed cohort contains only three finished events and 11 forecasts. Keep the current estimator frozen while resolving outcome semantics and collecting more independent results.

### Walk-Forward Results by Season

| Season | Lead Time | n | Mean Absolute Error | Median Signed Error | Range Coverage |
|---|---|---:|---:|---:|---:|
| 2023 | T-14 | 34 | 9.06% | -2.86% | 82.4% |
| 2023 | T-1 | 36 | 6.75% | +3.20% | 75.0% |
| 2024 | T-14 | 36 | 7.20% | +2.49% | 97.2% |
| 2024 | T-1 | 36 | 4.13% | +0.65% | 97.2% |
| 2025 | T-14 | 39 | 9.18% | -1.44% | 74.4% |
| 2025 | T-1 | 39 | 4.72% | -1.59% | 92.3% |
| 2026 | T-14 | 31 | 7.87% | +2.23% | 77.4% |
| 2026 | T-1 | 31 | 7.79% | +0.90% | 61.3% |

### Sealed Cohort

The freeze date remains September 27, 2026. The report accepts the original source hash and the verified display-only hash. An explicit custom hash still selects only its own rows. The daily ledger selects one published row per edition and date before the holdout filter, so equivalent source versions do not duplicate a forecast.

| Lead Time | n | Mean Absolute Error | Median Signed Error | Range Coverage |
|---|---:|---:|---:|---:|
| T-14 | 2 | 4.69% | +2.34% | 100.0% |
| T-7 | 3 | 8.69% | +11.06% | 33.3% |
| T-3 | 3 | 10.68% | +15.04% | 66.7% |
| T-1 | 3 | 11.78% | +9.73% | 33.3% |

## Admin Export and Scrape Reconciliation

The November 2 admin reports contain only tournament, section, bye, and registration-time fields. They contain no player identities. Each report lists one row per registration. The comparison uses each edition's maximum stored `entry_count`, as requested in [issue #180](https://github.com/HaterAndrew/chess-prediction/issues/180).

Admin status filters distinguish active, withdrawn, deleted, and rejected or pending payment registrations. The inspected differences show that an all-player export can include deleted rows, while some scrape peaks include withdrawals and others contain only the active count. World Open deliberately skips the shared withdrawal-page parser. These populations require an explicit count contract before any label replacement or regrading.

| Edition | Export Rows | Scrape Peak | Difference | Observation |
|---|---:|---:|---:|---|
| Atlantic City Open | 424 | 424 | +0 | Exact match. |
| Atlantic Open | 242 | 242 | +0 | Exact match. |
| Bradley Open | 209 | 209 | +0 | Exact match. |
| Central California Open | 169 | 169 | +0 | Exact match. |
| Chicago Class | 303 | 288 | +15 | 14 withdrawn; current active count exceeds the stored peak by 1. Historical difference unresolved. |
| Chicago Open | 918 | 917 | +1 | One deleted row. Current active + withdrawn equals 917. |
| Chicago Open Blitz | 140 | 134 | +6 | 6 withdrawn; active count equals the stored peak. |
| Cleveland Open | 179 | 179 | +0 | Exact match. |
| Continental Open | 280 | 266 | +14 | 14 withdrawn; active count equals the stored peak. |
| DC International | 107 | 107 | +0 | Exact match. |
| DC Open | 188 | 188 | +0 | Exact match. |
| Eastern Chess Congress (in New Jersey) | 447 | 446 | +1 | One deleted row. Current active + withdrawn equals 446. |
| Eastern Class Championships (in Connecticut) | 207 | 196 | +11 | 10 withdrawn and one deleted row; active count equals the stored peak. |
| Eastern Open | 15 | 15 | +0 | Exact match. |
| Hartford Open | 206 | 206 | +0 | Exact match. |
| Indianapolis Open | 180 | 180 | +0 | Exact match. |
| Kings Island Open | 95 | 95 | +0 | Exact match. |
| Los Angeles Open | 214 | 213 | +1 | Current admin has 211 active + 3 withdrawn. Stored scrape has 210 + 3; snapshots differ within the same day. |
| Midwest Class Championships | 237 | 226 | +11 | 11 withdrawn; active count equals the stored peak. |
| National Chess Congress | 135 | 135 | +0 | Exact match. |
| New York State Championship | 332 | 332 | +0 | Exact match. |
| New York State Open | 109 | 109 | +0 | Exact match. |
| North American Blitz Championship | 14 | 14 | +0 | Exact match. |
| North American Open | 394 | 394 | +0 | Exact match. |
| Pacific Coast Open | 395 | 394 | +1 | One deleted row. Current active + withdrawn equals 394. |
| Pittsburgh Open | 170 | 170 | +0 | Exact match. |
| Southern Open | 206 | 206 | +0 | Exact match. |
| World Open Under 13 Championship | 86 | 82 | +4 | 4 withdrawn; active count equals the stored peak. |
| World Open, lower sections | 96 | 93 | +3 | 3 withdrawn; active count equals the stored peak. |
| World Open, top 6 sections | 1111 | 1066 | +45 | 44 withdrawn; current active count exceeds the stored peak by 1. Historical difference unresolved. |

The World Open and Chicago Class residuals each compare a current active total with a lower historical peak. The available aggregate evidence does not identify the record or status change responsible. Keep both residuals open for record-history review. The Los Angeles difference concerns an event still taking entries and two snapshots from the same day.

Issue #180 should remain open until the owner resolves the two historical residuals and records the agreed population. Separate follow-ups can address omitted withdrawals and deleted-row treatment. This maintenance candidate does not replace final labels with export-row counts.

The count-only reports do not replace the full training export dated March 22. The isolated pipeline therefore exercises the existing CI behavior without that export. Existing warnings about the two relocated Eastern standings imports also remain visible.

## Dependency Dispositions

Each candidate passed its relevant local checks separately against the current main snapshot. The combined candidate also passed. The numerical-package comparison includes the old dependency environment for the baseline and the upgraded environment for the candidate.

| PR | Update | Local Disposition |
|---|---|---|
| [#219](https://github.com/HaterAndrew/chess-prediction/pull/219) | actions/setup-node 7.1.0 | Worker checks pass; upstream SHA verified |
| [#223](https://github.com/HaterAndrew/chess-prediction/pull/223) | Ruff 0.17.0 | Checksum, lint and full baseline suite pass |
| [#224](https://github.com/HaterAndrew/chess-prediction/pull/224) | pydantic 2.14.1 | Checksum, lint and full baseline suite pass |
| [#226](https://github.com/HaterAndrew/chess-prediction/pull/226) | rcssmin 1.3.0 | Checksum, lint and full baseline suite pass |
| [#227](https://github.com/HaterAndrew/chess-prediction/pull/227) | rjsmin 1.3.0 | Checksum, lint and full baseline suite pass |
| [#234](https://github.com/HaterAndrew/chess-prediction/pull/234) | Vitest 5.0.5 | Typecheck, tests and dry run pass |
| [#235](https://github.com/HaterAndrew/chess-prediction/pull/235) | actions/setup-python 7.1.0 | Python checks pass; upstream SHA verified; trigger gap corrected |
| [#236](https://github.com/HaterAndrew/chess-prediction/pull/236) | Workers Types 5.20261026.1 | Typecheck, tests and dry run pass |
| [#237](https://github.com/HaterAndrew/chess-prediction/pull/237) | pandas 3.1.0 and NumPy 2.5.4 | Python checks pass; forecast and backtest outputs unchanged |
| [#238](https://github.com/HaterAndrew/chess-prediction/pull/238) | Wrangler 4.152.0 | Typecheck, tests and dry run pass |
| [#239](https://github.com/HaterAndrew/chess-prediction/pull/239) | Anthropic SDK 1.3.0 | Real SDK transport fixtures pass for tool turns, file upload and API errors |

The Worker lock resolves the versions above. It retains TypeScript 7.0.2 and the existing undici override. All 105 changed lock entries use npm registry tarballs with SHA-512 integrity. The existing esbuild and workerd installation-script flags remain unchanged.

SDK 1.0 changed the default API version to October 21, 2026. The compatibility fixtures exercise the actual SDK serializer and parser with an injected transport. They verify tool-result continuation, multipart uploads, and a specific HTTP 503 error. They make no live model calls. A production API smoke check remains a release check.

## Host Retirement and Release Procedure

The local Worker configuration sets `workers_dev = false`. It retains the custom domain, preview URLs, bindings, and origins. The scraper proxy already targets `chessentries.com`. [Issue #179](https://github.com/HaterAndrew/chess-prediction/issues/179) also requests deletion of the retired `chess-ask` Worker.

1. Review the candidate diff before a commit.
2. Complete pre-push review before publication.
3. Obtain separate approval for a merge that deploys the Worker.
4. Confirm the Workers Builds deployment after the merge.
5. Verify the custom-domain page, data asset, scraper proxy, and Ask endpoint through an approved production route.
6. Verify that the production workers.dev alias returns 404.
7. Check the retired Worker's consumers and recovery records before deletion.
8. Obtain separate approval to delete the retired Worker.
9. Run the deletion command from the Worker directory with the pinned Node environment.

```sh
npx wrangler delete chess-ask
```

10. Verify that the retired workers.dev host returns 404.
11. Verify the custom-domain page again.
12. Check the next scheduled scrape for a healthy publication.

If the alias change causes a fault, restore `workers_dev = true` through a reviewed release. Preserve the custom-domain route. For a dependency regression, restore the prior manifests and lockfile through a reviewed revert. Retain the old Worker until its recovery records are sufficient.

## Evidence Limits

The hosted workflow trigger change will receive a native GitHub run after publication. The local negative and positive controls verify its path selection now. The checks above do not establish a new production deployment or a successful live Anthropic request.

The local candidate preserves generated data outside the development worktree. The original checkout and the March export remain unchanged.
