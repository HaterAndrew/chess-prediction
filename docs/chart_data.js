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

// ── UMD-style tail, as in util_core.js: a no-op in the page, the export for
// the node drivers. ──
if (typeof globalThis !== 'undefined') {
  globalThis.chartTableHTML = chartTableHTML;
  globalThis.stepValueAt = stepValueAt;
  globalThis.weeklyStops = weeklyStops;
  globalThis.historySlots = historySlots;
  globalThis.paceGap = paceGap;
}
if (typeof module !== 'undefined') {
  module.exports = { chartTableHTML, stepValueAt, weeklyStops, historySlots, paceGap };
}
