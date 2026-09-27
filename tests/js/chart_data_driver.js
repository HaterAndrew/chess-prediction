// Node driver for docs/chart_data.js — run by tests/test_chart_data_js.py.
// The charts' pure data shaping: the screen-reader tables and, as the chart
// PRs land, the layouts their plugins draw. Prints one JSON blob.
const path = require('path');
const D = require(path.join(__dirname, '..', '..', 'docs', 'chart_data.js'));

const out = {
  table: D.chartTableHTML({
    caption: 'Entries by edition',
    columns: ['Edition', 'Entries'],
    rows: [['2024', 312], ['<b>2025</b>', null], ['2026 "est"', '']],
  }),
  table_empty: D.chartTableHTML({ columns: ['A'], rows: [] }),
};

process.stdout.write(JSON.stringify(out));
