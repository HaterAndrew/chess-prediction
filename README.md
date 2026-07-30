# CCA Entry Predictor

Forecasts final entry counts for Continental Chess Association (CCA) tournaments.
A nightly pipeline scrapes live registration counts, re-runs the model, and
publishes point estimates with 80% confidence intervals to a static site.

Live site: https://haterandrew.github.io/chess-prediction/

## How it works

A GitHub Actions workflow (`.github/workflows/daily_update.yml`) runs every night:

1. `scrape_entries.py` pulls current entry counts from the CCA site.
2. `validate_scraped_data.py` and `data_health.py` gate the scrape with structural
   and sanity checks; a bad scrape fails loud instead of poisoning the model.
3. `04c_final_model.py` recomputes predictions, and `06_walk_in_multipliers.py`
   regenerates walk-in adjustments from historical standings.
4. `04d_website_data_v2.py` rebuilds the site payload, and `04e_performance_data.py`
   re-grades past prediction windows against actual final counts.
5. The workflow commits the refreshed `docs/` tree, which GitHub Pages serves as
   an installable PWA.

## Model

Trained on roughly 192K historical registration records. Two estimators blend by
lead time:

- a ratio model that projects the final count from today's count using each
  tournament family's historical pace curve, and
- a pooled regression that carries long lead times where pace data is thin.

The blend weights are fit on held-out years (`scripts/fit_ensemble_weights.py`)
rather than hand-picked. Walk-in multipliers account for players who register on
site. Expanding-window blind tests over 2022-2026 grade every prediction window.

This README carries no accuracy numbers on purpose. The site's model-health panel
renders them, single-sourced from the graded output, and
`tests/test_no_hardcoded_claims.py` blocks stale claims from re-entering prose.

## Ask tab

`worker/` holds a Cloudflare Worker that proxies the site's Ask tab to the
Anthropic API: a function-calling loop over the live site data, rate-limited per
IP, CORS-locked, and capped at a fixed daily spend. Setup instructions live in
`worker/README.md`.

## Repo layout

The 2026-07-30 decomposition moved the implementation into packages. The
numbered root scripts remain as thin shims: their filenames are the stable
interface the workflow, the subprocess timeout map, and older tooling key on,
and each re-exports its package's public surface so `import 04c...`-era call
sites keep working. Edit the packages, not the shims.

| Package | Owns | Shim |
|---|---|---|
| `shared/` | Repo paths, frozen-clock helpers, cross-module thresholds | — |
| `dataprep/` | Registration-export parsing, family repair, summary + curves | `01_data_prep.py` |
| `model/` | The N5v4 estimator: fitting, nowcast, recalibration, CIs, walk-ins | `04c_final_model.py` |
| `sitebuild/` | Site payload build: model cards, metadata cards, history, assembly | `04d_website_data_v2.py` |
| `perf/` | Expanding-window grading, year folds, performance report | `04e_performance_data.py` |
| `pipeline/` | Nightly orchestration: steps, runner, warning harvest, splicing, stamping | `auto_update.py` (keeps `main()`) |
| `fees/` | CCA code tables (single home), flyer discovery + parsing | `scrape_fees.py` |
| `scrapers/` | Entry/standings/historical scrapers + shared polite HTTP | `scrape_entries.py`, `scrape_standings.py`, `scrape_historical.py`, `scraper_utils.py` |
| `healthcheck/` | Prediction-output health scan (report, context, checks) | `data_health.py` (keeps the CLI + exit codes) |

| Path | Contents |
|---|---|
| `docs/` | The published site (GitHub Pages root): PWA shell, charts, service worker |
| `output/` | Tracked CSV corpus the model runs from; large generated artifacts stay ignored |
| `worker/` | Cloudflare Worker behind the Ask tab |
| `tests/` | Pytest suite covering the pipeline, grading, site data build, and Python/JS parity |
| `scripts/` | Standalone tools, including `golden_check.py` (see below) |
| `audit/` | Ledgers from code-audit passes and the fixes they produced |
| `likec4/` | Architecture model (`model.likec4`) + rendered views in `likec4/out/`; re-render with `npx likec4 export png -o likec4/out likec4` |

`hotel_audit.py` is a side tool that cross-checks hotel room-block usage against
entries; see `HOTEL_AUDIT_README.md`.

Two conventions the decomposition established:

- Behavior-preserving refactors of the model path gate on
  `scripts/golden_check.py`: capture `website_data.json` +
  `performance_data.json` baselines to a scratch dir, refactor, and compare
  with volatile keys stripped. Baselines are valid same-day only (the
  builders freeze TODAY at import).
- Tests monkeypatch the DEFINING module (`pipeline.config.SITE_DIR`,
  `perf.evaluation.OUTPUT_DIR`, `model.walkins.OUTPUT_DIR`), never a shim's
  re-exported copy — a patch on the shim does not reach package-internal
  readers.

## Running locally

```sh
pip install -r requirements-dev.txt
pytest
```

The one-time historical prep (`01_data_prep.py`) reads a raw registration export
that stays out of the repo. Everything downstream, including the test suite,
runs from the tracked CSVs under `output/`.
