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

| Path | Contents |
|---|---|
| `01_data_prep.py` through `06_walk_in_multipliers.py` | Numbered pipeline stages, orchestrated by `auto_update.py` |
| `scrape_*.py`, `validate_*.py` | Scrapers and the gates that police their output |
| `docs/` | The published site (GitHub Pages root): PWA shell, charts, service worker |
| `output/` | Tracked CSV corpus the model runs from; large generated artifacts stay ignored |
| `worker/` | Cloudflare Worker behind the Ask tab |
| `tests/` | Pytest suite covering the pipeline, grading, site data build, and Python/JS parity |
| `audit/` | Ledgers from code-audit passes and the fixes they produced |

`hotel_audit.py` is a side tool that cross-checks hotel room-block usage against
entries; see `HOTEL_AUDIT_README.md`.

## Running locally

```sh
pip install -r requirements-dev.txt
pytest
```

The one-time historical prep (`01_data_prep.py`) reads a raw registration export
that stays out of the repo. Everything downstream, including the test suite,
runs from the tracked CSVs under `output/`.
