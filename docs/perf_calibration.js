// perf_calibration.js — the Performance view's calibration strip: one dot per
// tournament at the point its final landed in its published 80% range, misses
// past the ends, and the counts against the 80% target (split from
// tab_performance.js, where a 10-bin histogram of 22 events stood in).
//
// The position is the PIT (perf/scoring.py pit_value): 0.1 and 0.9 are the
// range's ends, 0.5 the forecast. An honest range puts about 80% of the dots
// inside, spread evenly; a pile at the ends means it is too narrow.

const CAL_R = 5;

function _calEvents(view, T) {
  return (view.tournaments || []).map(t => {
    const p = (t.predictions || []).find(x => x.T === T);
    if (!p || typeof p.pit !== 'number') return null;
    return { pit: p.pit, inside: !!p.in_ci, family: t.family, year: (t.event_start || '').slice(0, 4),
             final: t.final_count, lo: p.ci_lower, hi: p.ci_upper };
  }).filter(Boolean);
}

function _calSVG(L, width) {
  const step = 2 * CAL_R + 1;
  const axisY = 10 + Math.max(1, L.rows) * step;
  const h = axisY + 22;
  const at = f => (f * width).toFixed(1);
  const ticks = [[0.1, 'Low End', 'start'], [0.5, 'Forecast', 'middle'], [0.9, 'High End', 'end']]
    .map(([f, label, anchor]) => `<line class="cal-tick" x1="${at(f)}" x2="${at(f)}" y1="${axisY}" y2="${axisY + 4}"/>` +
      `<text class="cal-label" x="${at(f)}" y="${axisY + 16}" text-anchor="${anchor}">${label}</text>`).join('');
  const dots = L.dots.map(d => {
    const cy = (axisY - CAL_R - 1 - d.row * step).toFixed(1);
    const place = d.inside ? 'inside' : d.pit < 0.5 ? 'below' : 'above';
    return `<circle class="cal-dot${d.inside ? '' : ' is-miss'}" cx="${d.x.toFixed(1)}" cy="${cy}" r="${d.inside ? CAL_R : CAL_R - 1}">` +
      `<title>${esc(d.family)} ${esc(d.year)}: final ${fmt(d.final)}, range ${fmt(d.lo)} to ${fmt(d.hi)}, ${place}</title></circle>`;
  }).join('');
  return `<svg class="cal-strip" viewBox="0 0 ${width} ${h}" width="${width}" height="${h}" aria-hidden="true">` +
    `<rect class="cal-range" x="${at(0.1)}" y="0" width="${at(0.8)}" height="${axisY}"/>` +
    `<line class="cal-axis" x1="0" x2="${width}" y1="${axisY}" y2="${axisY}"/>${ticks}${dots}</svg>`;
}

// The block for perfDrawScoring: title, counts, the strip's host, note, and
// the screen-reader table. The strip is drawn once the block is on the page
// (perfCalibrationFill), at the width it actually has.
function perfCalibrationHTML(view, T) {
  const events = _calEvents(view, T);
  const head = `<div class="perf-scoring-title">Calibration at T-${T}
    <span class="perf-scoring-sub">where each tournament's final landed in its 80% range (n=${events.length})</span></div>`;
  if (!events.length) {
    return `<div class="perf-scoring-block">${head}<div class="empty">This data file has no per-event calibration positions.</div></div>`;
  }
  const L = calibrationLayout(events, 1, 0);
  const counts = `<b>${L.inside} inside (${L.pctInside}%)</b> &middot; ${L.below} below &middot; ${L.above} above &middot; target 80% inside`;
  const rows = L.dots.map(d => [`${d.family} ${d.year}`, fmt(d.final), `${fmt(d.lo)} to ${fmt(d.hi)}`,
                                d.inside ? 'Inside' : d.pit < 0.5 ? 'Below' : 'Above']);
  const table = `<table class="sr-only">${chartTableHTML({
    caption: `Calibration at T-${T}: where each final landed`,
    columns: ['Tournament', 'Final', '80% Range', 'Landed'], rows })}</table>`;
  return `<div class="perf-scoring-block">${head}
    <div class="cal-counts" role="img" aria-label="${L.inside} of ${events.length} finals inside their 80% range (${L.pctInside}%), ${L.below} below, ${L.above} above; the target is 80% inside.">${counts}</div>
    <div class="cal-host" data-cal-t="${T}"></div>${table}
    <div class="perf-scoring-note">About 80% of the dots should sit inside the shaded range, spread evenly. A pile at the ends means the range is too narrow; a lean to one side means the forecast runs high or low.</div>
  </div>`;
}

function perfCalibrationFill(root, view) {
  const host = root.querySelector('.cal-host');
  if (!host) return;
  const events = _calEvents(view, Number(host.dataset.calT));
  const width = Math.max(200, Math.floor(host.clientWidth || 320));
  host.innerHTML = _calSVG(calibrationLayout(events, width, CAL_R), width);
}
