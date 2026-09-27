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

  // Calibration: dots stack where they would touch; counts by zone.
  cal: (() => {
    const L = D.calibrationLayout([
      { pit: 0.02, inside: false }, { pit: 0.03, inside: false },
      { pit: 0.5, inside: true }, { pit: 0.505, inside: true }, { pit: 0.51, inside: true },
      { pit: 0.7, inside: true }, { pit: 0.97, inside: false }, { pit: 1.0, inside: false },
    ], 200, 5);
    return { rows: L.rows, below: L.below, inside: L.inside, above: L.above, pct: L.pctInside,
             placed: L.dots.map(d => [Math.round(d.x), d.row]) };
  })(),

  // Label placement: the first clear spot around a point.
  seg_through: D.segmentHitsBox(0, 5, 20, 5, { l: 5, t: 0, r: 15, b: 10 }),
  seg_past: D.segmentHitsBox(0, 20, 20, 20, { l: 5, t: 0, r: 15, b: 10 }),
  spot_free: (() => { const s = D.chooseLabelSpot(100, 100, 40, 14, {}); return [s.x, s.y, s.clear]; })(),
  // A line leaving up and to the right blocks "above" (it crosses the
  // label's box); "below" is next and clear.
  spot_below: (() => { const s = D.chooseLabelSpot(100, 100, 40, 14,
    { segments: [[100, 100, 130, 60]], radius: 3 }); return [s.x, s.y, s.clear]; })(),
  // Above and below both blocked by taken boxes: a diagonal.
  spot_diag: (() => { const s = D.chooseLabelSpot(100, 100, 40, 14,
    { segments: [[100, 100, 100, 60], [100, 100, 100, 140]], radius: 3,
      taken: [{ l: 60, t: 60, r: 140, b: 80 }] }); return [s.x, s.y, s.clear]; })(),
  spot_none: D.chooseLabelSpot(100, 100, 40, 14, { area: { l: 95, t: 95, r: 105, b: 105 } }).clear,
  cross: [D.segmentsCross([0, 0, 10, 10], [0, 10, 10, 0]), D.segmentsCross([0, 0, 10, 0], [0, 5, 10, 5])],
  // A dot just under a line: "above" would put the line between label and
  // dot, so the label goes below even though "above" is clear of the line.
  spot_sight: D.chooseLabelSpot(100, 100, 40, 14,
    { segments: [[40, 96, 160, 96]], radius: 3, gap: 12, order: ['above', 'below'] }).spot,
  spot_order: D.chooseLabelSpot(100, 100, 40, 14, { order: ['left', 'right'] }).spot,
  // Near the area's right edge, "below" slides left to fit.
  spot_slide: (() => { const s = D.chooseLabelSpot(100, 100, 40, 14,
    { order: ['below'], area: { l: 0, t: 0, r: 110, b: 200 } }); return [s.x, s.clear]; })(),
  // Another label just under the point blocks the nearest "below"; the
  // next ring out clears it.
  spot_ring: (() => { const s = D.chooseLabelSpot(100, 100, 40, 14,
    { order: ['below'], taken: [{ l: 90, t: 106, r: 110, b: 109 }] }); return [s.y, s.clear]; })(),
  // A margin keeps a line's width off the box: a line 1px over the top of
  // "above" blocks it once the margin is 2.
  spot_margin: [0, 2].map(margin => D.chooseLabelSpot(100, 100, 40, 14,
    { segments: [[60, 78, 140, 78]], margin }).spot),
};

process.stdout.write(JSON.stringify(out));
