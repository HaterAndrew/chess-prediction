// tab_compare.js — side-by-side comparison tab, split verbatim from
// app.js (C15); its chart is compare_chart.js. Slot colours come from PALETTE at render time (not load
// time) so a theme switch recolours the next render; this file still loads
// after foundation.js because it calls into it.

// ══════════════════════════════════════════════════════════
// COMPARE (side-by-side tournament comparison)
// ══════════════════════════════════════════════════════════
const COMPARE_KEY = 'cca_compare';
function compareColors() { return PALETTE.series.slice(); }
function compareColorsDim() { return PALETTE.series.map(c => themeRgba(c, 0.15)); }
let _compareSlots = [];
let _compareChart = null;

// The saved picks, or null when the visitor has never picked: the tab then
// opens on the selected tournament and its prior edition (renderCompareTab).
function getCompareSlots() {
  try {
    const raw = localStorage.getItem(COMPARE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}
function saveCompareSlots(slots) {
  localStorage.setItem(COMPARE_KEY, JSON.stringify(slots));
}

function renderCompareTab() {
  const el = document.getElementById('compareContent');
  if (!el) return;
  const saved = getCompareSlots();
  _compareSlots = saved || [];
  const tournaments = TOURNAMENT_DATA.tournaments;

  // Never picked: open on the selected tournament and the same family's
  // prior edition. The seed lives in memory only; the first change to a slot
  // saves what is on screen, so removing a seeded pick sticks.
  if (saved === null && typeof selectedIndex === 'number' && tournaments[selectedIndex]) {
    const active = tournaments[selectedIndex];
    _compareSlots = [selectedIndex];
    const priorIdx = tournaments.findIndex((t, i) =>
      i !== selectedIndex && t.family === active.family && Number(t.year) === Number(active.year) - 1
    );
    if (priorIdx >= 0) _compareSlots.push(priorIdx);
  }

  // Build selector UI
  let selectorHTML = '<div class="compare-selectors">';
  for (let s = 0; s < 3; s++) {
    const currentIdx = _compareSlots[s];
    const colorDot = `<span class="compare-color-dot series-${s + 1}" aria-hidden="true"></span>`;
    selectorHTML += `<div class="compare-selector">
      ${colorDot}
      <select class="field compare-dropdown" data-inputact="compare-slot-changed" data-slot="${s}" aria-label="Tournament ${s + 1}">
        <option value="">Select tournament...</option>
        ${tournaments.map((t, i) => {
          const sel = i === currentIdx ? 'selected' : '';
          // Year first, so a narrow picker cuts the end of the name, not the year.
          const label = t.year + ' ' + esc(t.family);
          return `<option value="${i}" ${sel}>${label}</option>`;
        }).join('')}
      </select>
      ${currentIdx != null ? `<button class="icon-button compare-remove-btn" data-act="compare-slot-remove" data-slot="${s}" title="Remove" aria-label="Remove tournament ${s + 1}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg></button>` : ''}
    </div>`;
  }
  selectorHTML += '</div>';

  // Build stat table if 2+ selected
  const selected = _compareSlots.map(i => ({ idx: i, t: tournaments[i] })).filter(x => x.t);
  let statsHTML = '';
  let chartHTML = '';
  let insightHTML = '';

  if (selected.length >= 2) {
    // Each event's column is headed by its colour dot and name; a phone keeps
    // the dot only, since the pickers above already name the picks.
    statsHTML = '<div class="compare-table-wrap"><table class="compare-table"><thead><tr><th>Stat</th>';
    selected.forEach((s, ci) => {
      statsHTML += `<th class="series-${ci + 1}"><span class="compare-color-dot series-${ci + 1}" aria-hidden="true"></span>`
        + `<span class="compare-th-name">${esc(s.t.family)} ${s.t.year}</span></th>`;
    });
    statsHTML += '</tr></thead><tbody>';

    const rows = [
      { label: 'Status', fn: t => {
        const s = t.status === 'live' ? 'Upcoming' : t.status === 'complete' ? 'Complete' : 'Historical';
        const kind = t.status === 'live' ? 'live' : t.status === 'complete' ? 'complete' : 'hist';
        return `<span class="pill pill-${kind}">${t.status === 'live' ? '<span class="live-dot"></span>' : ''}${s}</span>`;
      }},
      { label: 'Current Count', fn: t => fmt(t.current_count) },
      { label: 'Predicted Final', live: true, fn: t => fmt(t.point_estimate) },
      { label: 'CI Range', live: true, fn: t => t.ci_lower && t.ci_upper ? `${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}` : '—' },
      { label: 'Days Remaining', live: true, fn: t => t.days_remaining != null ? t.days_remaining : '—' },
      { label: 'Historical Avg', fn: t => t.historical && t.historical.length > 0 ? fmt(Math.round(t.historical.reduce((s, h) => s + h.count, 0) / t.historical.length)) : '—' },
      // The payload field is event_start. Reading a non-existent event_date
      // rendered the em-dash placeholder for every tournament in every
      // comparison, which looked like missing data rather than a bug.
      { label: 'Event Date', fn: t => t.event_start ? fmtDate(t.event_start) : '—' },
    ];

    // The forecast rows say nothing when every pick has finished.
    const anyLive = selected.some(s => s.t.status === 'live');
    rows.filter(row => anyLive || !row.live).forEach(row => {
      statsHTML += `<tr><td class="compare-stat-label" data-stat="${esc(row.label)}">${row.label}</td>`;
      selected.forEach(s => { statsHTML += `<td data-label="${esc(s.t.family)} ${s.t.year}">${row.fn(s.t)}</td>`; });
      statsHTML += '</tr>';
    });
    statsHTML += '</tbody></table></div>';

    // Insight: compare predicted finals
    const preds = selected.map(s => ({ name: s.t.family, pred: s.t.point_estimate || 0 }));
    const maxPred = preds.reduce((a, b) => a.pred > b.pred ? a : b);
    const insights = [];
    preds.forEach(p => {
      if (p.name !== maxPred.name && maxPred.pred > 0 && p.pred > 0) {
        const pctAhead = ((maxPred.pred - p.pred) / p.pred * 100).toFixed(0);
        insights.push(`<strong>${esc(maxPred.name)}</strong> is predicted ${pctAhead}% higher than <strong>${esc(p.name)}</strong>`);
      }
    });
    if (insights.length > 0) {
      insightHTML = `<div class="compare-insights">${insights.map(i => `<div class="compare-insight">${i}</div>`).join('')}</div>`;
    }

    // Chart container
    chartHTML = `<div class="compare-chart-wrap"><canvas id="compareChart"></canvas></div>`;
  } else if (selected.length < 2) {
    statsHTML = `<div class="empty compare-empty">
      <div>Pick at least two tournaments to compare.</div>
    </div>`;
  }

  // v4 U3 (audit/AUDIT_2026-07-26.md): the <2-selected path re-renders without
  // a canvas, so destroy before the innerHTML write detaches it — otherwise the
  // instance and its ResizeObserver stay live on the orphaned canvas.
  if (_compareChart) { _compareChart.destroy(); _compareChart = null; }
  el.innerHTML = selectorHTML + insightHTML + statsHTML + chartHTML;

  // Render chart if 2+
  if (selected.length >= 2) renderCompareChart(selected);
}

function compareSlotChanged(slotIdx, val) {
  _compareSlots = getCompareSlots() || _compareSlots.slice();
  const idx = val !== '' ? parseInt(val, 10) : null;
  // Remove if already in another slot
  if (idx != null) _compareSlots = _compareSlots.filter(i => i !== idx);
  // Set or clear the slot
  while (_compareSlots.length <= slotIdx) _compareSlots.push(null);
  _compareSlots[slotIdx] = idx;
  // Compact: remove trailing nulls
  _compareSlots = _compareSlots.filter(i => i != null);
  saveCompareSlots(_compareSlots);
  renderCompareTab();
}

function compareSlotRemove(slotIdx) {
  _compareSlots = getCompareSlots() || _compareSlots.slice();
  if (slotIdx < _compareSlots.length) _compareSlots.splice(slotIdx, 1);
  saveCompareSlots(_compareSlots);
  renderCompareTab();
}
