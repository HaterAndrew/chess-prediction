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

  // Step lookup on a cumulative series: the latest point at or before x.
  step_before: D.stepValueAt([{ x: 10, y: 1 }, { x: 20, y: 5 }], 5),
  step_on: D.stepValueAt([{ x: 10, y: 1 }, { x: 20, y: 5 }], 20),
  step_between: D.stepValueAt([{ x: 10, y: 1 }, { x: 20, y: 5 }, { x: 30, y: 9 }], 25),
  step_after: D.stepValueAt([{ x: 10, y: 1 }, { x: 20, y: 5 }], 21),
  step_empty: D.stepValueAt([], 1),

  // Weekly rows anchored on event day, oldest first, never before start.
  weekly: D.weeklyStops(new Date(2026, 9, 9).getTime(), new Date(2026, 8, 20).getTime())
    .map(ms => { const d = new Date(ms); return [d.getMonth() + 1, d.getDate()]; }),

  // History slots: gaps between editions become one labelled empty slot.
  slots: D.historySlots(
    [{ year: 2018, count: 300 }, { year: 2019, count: 310, adjusted: 'top6', count_raw: 420 },
     { year: 2022, count: 280 }, { year: 2023, count: 305 }],
    { year: 2025, count: 330 }).map(x => [x.label, x.count, x.kind, x.flag ? x.flag.raw : null]),
  slots_none: D.historySlots([], { year: 2026, count: 10 }).map(x => [x.label, x.kind]),

  pace_behind: D.paceGap(32.4, 22.1),
  pace_ahead_one: D.paceGap(40, 41.2),
  pace_on: D.paceGap(50, 50.3),
};

process.stdout.write(JSON.stringify(out));
