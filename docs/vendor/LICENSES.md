# Vendored scripts

Served from this origin instead of a CDN so the first paint needs no second
connection. Each file is the published build, byte for byte; its sha384 is
pinned in `pipeline/bundling.py` and checked by `tests/test_bundling.py`.
Upgrade by replacing the file and the pinned hash together.

- Chart.js 4.5.1 (`chart.umd.min.js`): MIT License, Chart.js Contributors. https://www.chartjs.org
- chartjs-adapter-date-fns 3.0.0 (`chartjs-adapter-date-fns.bundle.min.js`, bundles date-fns): MIT License, chartjs-adapter-date-fns Contributors and date-fns contributors. https://github.com/chartjs/chartjs-adapter-date-fns
