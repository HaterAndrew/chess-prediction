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

// ── UMD-style tail, as in util_core.js: a no-op in the page, the export for
// the node drivers. ──
if (typeof globalThis !== 'undefined') {
  globalThis.chartTableHTML = chartTableHTML;
}
if (typeof module !== 'undefined') {
  module.exports = { chartTableHTML };
}
