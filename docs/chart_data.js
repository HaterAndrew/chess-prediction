// chart_data.js — pure data shaping for the charts: no DOM, no Chart.js, so
// the node drivers under tests/js/ can run it. chart_kit.js and the chart
// files call it; a classic script like util_core.js, mirrored onto
// globalThis and module.exports at the foot for the drivers.

function _cellText(v) {
  if (v == null) return '';
  return String(v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// A chart's data as a table for screen readers: a caption, one header row,
// then the rows. Every cell is escaped; a missing value reads as a dash.
function chartTableHTML(spec) {
  const cols = spec.columns || [];
  const head = cols.map(c => `<th scope="col">${_cellText(c)}</th>`).join('');
  const body = (spec.rows || []).map(r => '<tr>' + r.map((v, i) => {
    const cell = v == null || v === '' ? '—' : _cellText(v);
    return i === 0 ? `<th scope="row">${cell}</th>` : `<td>${cell}</td>`;
  }).join('') + '</tr>').join('');
  const caption = spec.caption ? `<caption>${_cellText(spec.caption)}</caption>` : '';
  return `${caption}<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
}

// The value a cumulative series holds at time x: the latest point at or
// before x, or null outside the series' own span. points: [{x, y}] sorted.
function stepValueAt(points, x) {
  if (!points || !points.length || x < points[0].x || x > points[points.length - 1].x) return null;
  let lo = 0, hi = points.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (points[mid].x <= x) lo = mid; else hi = mid - 1;
  }
  return points[lo].y;
}

// Every seventh day back from end (a timestamp) while on or after start,
// oldest first: the rows of the main chart's table, anchored on event day.
function weeklyStops(endMs, startMs) {
  const out = [];
  for (let k = 0; ; k++) {
    const d = new Date(endMs);
    d.setDate(d.getDate() - 7 * k);
    if (d.getTime() < startMs) break;
    out.push(d.getTime());
  }
  return out.reverse();
}

// The History bars' slots, oldest first: each past edition, an empty slot
// for every run of missing years between editions ("2020–21"), then this
// edition. past: [{year, count, adjusted, count_raw}]; current: {year, count}.
// A slot: {label, year, count (null for a gap), kind: past|gap|current, flag}.
function historySlots(past, current) {
  const eds = (past || []).map(h => ({
    label: h.adjusted ? `${h.year}*` : String(h.year), year: h.year, count: h.count, kind: 'past',
    flag: h.adjusted ? { kind: h.adjusted, raw: h.count_raw } : null,
  }));
  eds.push({ label: String(current.year), year: current.year, count: current.count, kind: 'current', flag: null });
  const out = [];
  eds.forEach((e, i) => {
    const prev = i > 0 ? eds[i - 1].year : null;
    if (prev != null && e.year - prev > 1) {
      const a = prev + 1, b = e.year - 1;
      const label = a === b ? String(a) : `${a}–${String(b).slice(-2)}`;
      out.push({ label, year: null, count: null, kind: 'gap', flag: null });
    }
    out.push(e);
  });
  return out;
}

// Where this event stands against a typical year at the same point, in
// percentage points of the final: {diff, text}. Under half a point is on pace.
function paceGap(typicalPct, thisPct) {
  const diff = Math.round((thisPct - typicalPct) * 10) / 10;
  if (Math.abs(diff) < 0.5) return { diff, text: 'on pace' };
  const pts = Math.abs(Math.round(diff));
  return { diff, text: `${pts} pt${pts === 1 ? '' : 's'} ${diff > 0 ? 'ahead' : 'behind'}` };
}

// The calibration strip's layout: each event at x = pit × width (the 80%
// range runs from 0.1 to 0.9), stacked in rows where dots of radius r would
// touch, lowest row first. events: [{pit, inside, ...}]. Returns the dots
// with x and row, the counts, and the share inside.
function calibrationLayout(events, width, r) {
  const gap = 2 * r + 1;
  const rows = [];
  const dots = events
    .map(e => Object.assign({}, e, { x: Math.min(width - r, Math.max(r, e.pit * width)) }))
    .sort((a, b) => a.x - b.x);
  dots.forEach(d => {
    let row = 0;
    while (rows[row] != null && d.x - rows[row] < gap) row++;
    rows[row] = d.x;
    d.row = row;
  });
  const inside = dots.filter(d => d.inside).length;
  const below = dots.filter(d => !d.inside && d.pit < 0.5).length;
  const above = dots.length - inside - below;
  return { dots, inside, below, above, rows: rows.length,
           pctInside: dots.length ? Math.round(inside / dots.length * 100) : 0 };
}

// Does the segment (x0, y0)–(x1, y1) enter the box {l, t, r, b}?
// (Liang–Barsky clipping.)
function segmentHitsBox(x0, y0, x1, y1, b) {
  let t0 = 0, t1 = 1;
  const dx = x1 - x0, dy = y1 - y0;
  const edges = [[-dx, x0 - b.l], [dx, b.r - x0], [-dy, y0 - b.t], [dy, b.b - y0]];
  for (const [p, q] of edges) {
    if (p === 0) { if (q < 0) return false; continue; }
    const r = q / p;
    if (p < 0) { if (r > t1) return false; if (r > t0) t0 = r; }
    else { if (r < t0) return false; if (r < t1) t1 = r; }
  }
  return t0 < t1;
}
function boxesMeet(a, b) { return a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b; }
// Do two segments cross (touching counts)?
function segmentsCross(a, b) {
  const side = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
  const [p1, p2, q1, q2] = [[a[0], a[1]], [a[2], a[3]], [b[0], b[1]], [b[2], b[3]]];
  return side(p1, p2, q1) !== side(p1, p2, q2) && side(q1, q2, p1) !== side(q1, q2, p2);
}

// The spots a label can take round a point, nearest first.
const LABEL_SPOTS = ['above', 'below', 'above-right', 'above-left', 'below-right', 'below-left', 'right', 'left'];

// Where a label w × h goes beside the point (x, y): the first spot in
// opts.order (default LABEL_SPOTS) whose box, grown by opts.margin, clears
// every data segment [x0, y0, x1, y1] and every taken box (dots, earlier
// labels), stays inside opts.area {l, t, r, b}, and sees its point: the
// sight line from the edge of the point's dot (opts.radius) to the box
// crosses no data segment, so a label never sits across a line from its
// dot. The spots sit opts.gap
// from the point, then step out opts.step at a time (opts.rings in all); a
// label straight above or below slides sideways to stay inside the area.
// Returns the box centre, the box, the spot and whether it is clear; with
// no clear spot, the first one.
function chooseLabelSpot(x, y, w, h, opts) {
  const o = opts || {};
  const segments = o.segments || [], taken = o.taken || [], area = o.area;
  const m = o.margin || 0, order = o.order || LABEL_SPOTS, r = o.radius || 0;
  const gap = o.gap == null ? 7 : o.gap, step = o.step || 6, rings = o.rings || 3;
  const at = (name, d) => {
    const dx = w / 2 + d, dy = h / 2 + d;
    const off = { above: [0, -dy], below: [0, dy], 'above-right': [dx, -dy], 'above-left': [-dx, -dy],
                  'below-right': [dx, dy], 'below-left': [-dx, dy], right: [dx + 2, 0], left: [-dx - 2, 0] }[name];
    let cx = x + off[0];
    if (area && !off[0]) cx = Math.min(Math.max(cx, area.l + w / 2), area.r - w / 2);
    const cy = y + off[1];
    return { x: cx, y: cy, spot: name, box: { l: cx - w / 2, r: cx + w / 2, t: cy - h / 2, b: cy + h / 2 } };
  };
  const clear = b => {
    if (area && (b.l < area.l || b.r > area.r || b.t < area.t || b.b > area.b)) return false;
    const g = { l: b.l - m, r: b.r + m, t: b.t - m, b: b.b + m };
    return !segments.some(sg => segmentHitsBox(sg[0], sg[1], sg[2], sg[3], g)) && !taken.some(tb => boxesMeet(tb, g)) && sees(b);
  };
  const sees = b => {
    const px = Math.min(Math.max(x, b.l), b.r), py = Math.min(Math.max(y, b.t), b.b);
    const d = Math.hypot(px - x, py - y);
    if (d <= r) return true;
    const sight = [x + (px - x) * r / d, y + (py - y) * r / d, px, py];
    return !segments.some(sg => segmentsCross(sight, sg));
  };
  for (let k = 0; k < rings; k++) {
    for (const name of order) {
      const c = at(name, gap + k * step);
      if (clear(c.box)) return Object.assign(c, { clear: true });
    }
  }
  return Object.assign(at(order[0], gap), { clear: false });
}

// ── UMD-style tail, as in util_core.js: a no-op in the page, the export for
// the node drivers. ──
if (typeof globalThis !== 'undefined') {
  globalThis.chartTableHTML = chartTableHTML;
  globalThis.stepValueAt = stepValueAt;
  globalThis.weeklyStops = weeklyStops;
  globalThis.historySlots = historySlots;
  globalThis.paceGap = paceGap;
  globalThis.calibrationLayout = calibrationLayout;
  globalThis.segmentHitsBox = segmentHitsBox;
  globalThis.segmentsCross = segmentsCross;
  globalThis.chooseLabelSpot = chooseLabelSpot;
}
if (typeof module !== 'undefined') {
  module.exports = { chartTableHTML, stepValueAt, weeklyStops, historySlots, paceGap, calibrationLayout,
    segmentHitsBox, segmentsCross, chooseLabelSpot };
}
