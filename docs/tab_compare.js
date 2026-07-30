// tab_compare.js — side-by-side comparison tab, split verbatim from
// app.js (C15). COMPARE_COLORS reads PALETTE at load time, so this file
// must load after foundation.js.

// ══════════════════════════════════════════════════════════
// COMPARE (side-by-side tournament comparison)
// ══════════════════════════════════════════════════════════
const COMPARE_KEY = 'cca_compare';
const COMPARE_COLORS = [PALETTE.blue, PALETTE.gold, PALETTE.green];
const COMPARE_COLORS_DIM = ['rgba(88,166,255,0.15)', 'rgba(240,192,64,0.15)', 'rgba(63,185,80,0.15)'];
let _compareSlots = [];
let _compareChart = null;

function getCompareSlots() {
  try {
    const raw = localStorage.getItem(COMPARE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) { return []; }
}
function saveCompareSlots(slots) {
  localStorage.setItem(COMPARE_KEY, JSON.stringify(slots));
}

function addToCompare(idx) {
  _compareSlots = getCompareSlots();
  if (_compareSlots.includes(idx)) return;
  if (_compareSlots.length >= 3) {
    alert('Compare supports up to 3 tournaments. Remove one first.');
    return;
  }
  _compareSlots.push(idx);
  saveCompareSlots(_compareSlots);
  updateCompareBtn();
  if (_compareSlots.length >= 2) {
    switchPageTab('compare');
  }
}

function removeFromCompare(idx) {
  _compareSlots = getCompareSlots();
  const pos = _compareSlots.indexOf(idx);
  if (pos >= 0) _compareSlots.splice(pos, 1);
  saveCompareSlots(_compareSlots);
  updateCompareBtn();
  if (_currentTab === 'compare') renderCompareTab();
}

function addToCompareSelected() {
  if (selectedIndex != null) addToCompare(selectedIndex);
}

function updateCompareBtn() {
  const btn = document.getElementById('compareAddBtn');
  if (!btn) return;
  _compareSlots = getCompareSlots();
  const inCompare = selectedIndex != null && _compareSlots.includes(selectedIndex);
  btn.classList.toggle('compare-active', inCompare);
  btn.title = inCompare ? 'Remove from Compare' : 'Add to Compare';
  if (inCompare) {
    btn.onclick = function() { removeFromCompare(selectedIndex); };
  } else {
    btn.onclick = function() { addToCompareSelected(); };
  }
}

function renderCompareTab() {
  const el = document.getElementById('compareContent');
  if (!el) return;
  _compareSlots = getCompareSlots();
  const tournaments = TOURNAMENT_DATA.tournaments;

  // Empty state: pre-fill with active tournament + same family last year so
  // the panel opens with a useful default view. User can still pick others;
  // we only seed in-memory, don't persist to localStorage until user adds.
  if (_compareSlots.length === 0 && typeof selectedIndex === 'number' && tournaments[selectedIndex]) {
    const active = tournaments[selectedIndex];
    _compareSlots = [selectedIndex];
    const priorIdx = tournaments.findIndex((t, i) =>
      i !== selectedIndex && t.family === active.family && Number(t.year) === Number(active.year) - 1
    );
    if (priorIdx >= 0) _compareSlots.push(priorIdx);
  }

  // One-line caption above the selectors
  let captionHTML = '<div class="compare-caption" style="font-size:var(--fs-2);color:var(--muted);margin:0 0 10px">Pick up to 3 tournaments to compare entry trajectories side-by-side.</div>';

  // Build selector UI
  let selectorHTML = captionHTML + '<div class="compare-selectors">';
  for (let s = 0; s < 3; s++) {
    const currentIdx = _compareSlots[s];
    const colorDot = `<span class="compare-color-dot" style="background:${COMPARE_COLORS[s]}"></span>`;
    selectorHTML += `<div class="compare-selector">
      ${colorDot}
      <select class="compare-dropdown" data-inputact="compare-slot-changed" data-slot="${s}">
        <option value="">Select tournament...</option>
        ${tournaments.map((t, i) => {
          const sel = i === currentIdx ? 'selected' : '';
          const label = esc(t.family) + ' ' + t.year;
          return `<option value="${i}" ${sel}>${label}</option>`;
        }).join('')}
      </select>
      ${currentIdx != null ? `<button class="compare-remove-btn" data-act="compare-slot-remove" data-slot="${s}" title="Remove">&#10005;</button>` : ''}
    </div>`;
  }
  selectorHTML += '</div>';

  // Build stat table if 2+ selected
  const selected = _compareSlots.map(i => ({ idx: i, t: tournaments[i] })).filter(x => x.t);
  let statsHTML = '';
  let chartHTML = '';
  let insightHTML = '';

  if (selected.length >= 2) {
    statsHTML = '<div class="compare-table-wrap"><table class="compare-table"><thead><tr><th>Stat</th>';
    selected.forEach((s, ci) => {
      statsHTML += `<th style="color:${COMPARE_COLORS[ci]}">${esc(s.t.family)} ${s.t.year}</th>`;
    });
    statsHTML += '</tr></thead><tbody>';

    const rows = [
      { label: 'Status', fn: t => {
        const s = t.status === 'live' ? 'Live' : t.status === 'complete' ? 'Complete' : 'Upcoming';
        return `<span class="mini-badge badge-${t.status === 'live' ? 'live' : t.status === 'complete' ? 'complete' : 'upcoming'}">${s}</span>`;
      }},
      { label: 'Current Count', fn: t => fmt(t.current_count) },
      { label: 'Predicted Final', fn: t => fmt(t.point_estimate) },
      { label: 'CI Range', fn: t => t.ci_lower && t.ci_upper ? `${fmt(t.ci_lower)} – ${fmt(t.ci_upper)}` : '—' },
      { label: 'Days Remaining', fn: t => t.days_remaining != null ? t.days_remaining : '—' },
      { label: 'Historical Avg', fn: t => t.historical && t.historical.length > 0 ? fmt(Math.round(t.historical.reduce((s, h) => s + h.count, 0) / t.historical.length)) : '—' },
      { label: 'Event Date', fn: t => t.event_date ? fmtDate(t.event_date) : '—' },
    ];

    rows.forEach(row => {
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
    statsHTML = `<div class="compare-empty">
      <div style="font-size:2.5rem;margin-bottom:12px">&#9878;</div>
      <div style="font-size:1rem;font-weight:600;margin-bottom:6px">Select at least 2 tournaments to compare</div>
      <div style="font-size:var(--fs-3);color:var(--muted)">Use the dropdowns above or click &#9878; on any tournament in the Predictions tab</div>
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
  _compareSlots = getCompareSlots();
  const idx = val !== '' ? parseInt(val, 10) : null;
  // Remove if already in another slot
  if (idx != null) _compareSlots = _compareSlots.filter(i => i !== idx);
  // Set or clear the slot
  while (_compareSlots.length <= slotIdx) _compareSlots.push(null);
  _compareSlots[slotIdx] = idx;
  // Compact: remove trailing nulls
  _compareSlots = _compareSlots.filter(i => i != null);
  saveCompareSlots(_compareSlots);
  updateCompareBtn();
  renderCompareTab();
}

function compareSlotRemove(slotIdx) {
  _compareSlots = getCompareSlots();
  if (slotIdx < _compareSlots.length) _compareSlots.splice(slotIdx, 1);
  saveCompareSlots(_compareSlots);
  updateCompareBtn();
  renderCompareTab();
}

function renderCompareChart(selected) {
  if (_compareChart) { _compareChart.destroy(); _compareChart = null; }
  const canvas = document.getElementById('compareChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  // Build datasets from each tournament's ACTUAL daily_data (current edition's
  // real trajectory), not the smoothed prediction curve. y-axis is normalized
  // to % of predicted final, so different-sized tournaments compare cleanly
  // on the same scale. Each live tournament gets:
  //   - A solid line of its actual trajectory so far (this year's daily_data)
  //   - A dashed line of its prior year at T-N (where available) for context
  //   - A "today" dot at the latest data point
  // Completed tournaments get a single solid trace of their full daily_data.
  const datasets = [];
  selected.forEach((s, ci) => {
    const t = s.t;
    const color = COMPARE_COLORS[ci];
    const dimColor = COMPARE_COLORS_DIM[ci];
    // The y scaling target — predicted for live, actual final for completed.
    const target = (t.status === 'live')
      ? (t.point_estimate || 1)
      : (t.current_count || 1);
    if (target <= 0) return;

    // Current edition trajectory (solid line).
    if (t.daily_data && t.daily_data.length > 0 && t.event_start) {
      // Same contract as the main chart (v3 P1): draw the sanitised series,
      // never the raw array — raw points above the scraped total are
      // impossible and skew the normalized %.
      const dd = (typeof DailySeries !== 'undefined')
        ? DailySeries.sanitizeSeries(t.daily_data, {
            currentCount: t.current_count, isLive: t.status === 'live' }).points
        : t.daily_data;
      // Guard block (not an early return): an empty sanitised series must not
      // silently drop this tournament's prior-year trace below.
      if (dd.length) {
        // Convert daily_data ([day_idx, cumulative]) to (days_before, %).
        const lastDay = dd[dd.length - 1][0];
        const data = dd.map(p => ({
          x: lastDay - p[0] + (t.days_remaining || 0),
          y: (p[1] / target) * 100,
        }));
        datasets.push({
          label: `${t.family} ${t.year}`,
          data,
          borderColor: color,
          backgroundColor: dimColor,
          fill: ci === 0,
          borderWidth: 2.5,
          borderCapStyle: 'round',
          pointRadius: 0,
          pointHoverRadius: 5,
          tension: 0.25,
        });
        // Today dot — the very last actual data point.
        if (t.status === 'live') {
          const last = data[data.length - 1];
          datasets.push({
            label: `${t.family} · Today`,
            data: [last],
            borderColor: color,
            backgroundColor: color,
            pointRadius: 7,
            pointStyle: 'circle',
            pointBorderWidth: 2,
            // Canvas cannot resolve CSS custom properties; 'var(--bg)' here
            // silently painted the ring black on every theme.
            pointBorderColor: PALETTE.bg,
            showLine: false,
          });
        }
      }
    }

    // Prior-year context — dashed line of the most recent historical edition
    // (model uses this as part of its training). Surfaces "is this year
    // tracking ahead/behind last year at the same T?" visually.
    if (t.status === 'live' && t.historical && t.historical.length > 0) {
      const prior = t.historical[t.historical.length - 1];
      if (prior && prior.daily_data && prior.daily_data.length > 0
          && prior.count && prior.count > 0) {
        const priorTarget = prior.count;
        const pdd = (typeof DailySeries !== 'undefined')
          ? DailySeries.sanitizeSeries(prior.daily_data, {
              currentCount: prior.count, isLive: false }).points
          : prior.daily_data;
        const priorLast = pdd.length ? pdd[pdd.length - 1][0] : 0;
        const priorData = pdd.map(p => ({
          x: priorLast - p[0],
          y: (p[1] / priorTarget) * 100,
        }));
        datasets.push({
          label: `${t.family} · ${prior.year} (prior)`,
          data: priorData,
          borderColor: color,
          borderDash: [4, 4],
          borderWidth: 1.5,
          borderCapStyle: 'round',
          pointRadius: 0,
          pointHoverRadius: 3,
          tension: 0.25,
          fill: false,
        });
      }
    }

    // Final-count fallback: if we couldn't build a daily line (e.g. no
    // daily_data for a completed tournament), at least render a single
    // marker at x=0 (event day) at 100%.
    if (!t.daily_data || t.daily_data.length === 0) {
      datasets.push({
        label: `${t.family} ${t.year}`,
        data: [{ x: 0, y: 100 }],
        borderColor: color, backgroundColor: color,
        pointRadius: 8, pointStyle: 'circle', showLine: false,
      });
    }
  });

  if (datasets.length === 0) return;

  // Direct end labels for the primary traces (desktop only; mobile keeps the
  // legend). The x scale is reverse:true, so a trace's "now" endpoint (lowest
  // days-before value) renders at the RIGHT edge — labels sit left of the
  // endpoint and clamp inside the chart area. Vertical collisions stack the
  // same way the marker pills do.
  const compareEndLabels = {
    id: 'compareEndLabels',
    afterDraw(chartInstance) {
      if (_mobileVP()) return;
      const area = chartInstance.chartArea;
      const ctx2 = chartInstance.ctx;
      const drawn = [];
      chartInstance.data.datasets.forEach((ds, i) => {
        if (!ds.label || ds.label.includes('· Today') || ds.label.includes('(prior)')) return;
        const meta = chartInstance.getDatasetMeta(i);
        if (!meta.visible || !meta.data.length) return;
        const end = meta.data[meta.data.length - 1];
        ctx2.save();
        ctx2.font = 'bold 11px -apple-system, system-ui, sans-serif';
        ctx2.textAlign = 'left';
        const textW = ctx2.measureText(ds.label).width;
        const pillW = textW + 12;
        const pillH = 16;
        let px = end.x - 10 - pillW;
        if (px < area.left) px = Math.min(end.x + 10, area.right - pillW);
        let py = end.y - pillH / 2;
        if (py < area.top) py = area.top;
        if (py + pillH > area.bottom) py = area.bottom - pillH;
        // Dodge vertically past any already-drawn label rect.
        let guard = 0;
        while (guard++ < 6 && drawn.some(d =>
            !(px + pillW < d.x || px > d.x + d.w || py + pillH < d.y || py > d.y + d.h))) {
          py += pillH + 3;
          if (py + pillH > area.bottom) { py = area.top; break; }
        }
        drawn.push({ x: px, y: py, w: pillW, h: pillH });
        ctx2.fillStyle = themeRgba(PALETTE.surface, 0.85);
        ctx2.beginPath();
        ctx2.roundRect(px, py, pillW, pillH, 4);
        ctx2.fill();
        ctx2.strokeStyle = ds.borderColor;
        ctx2.globalAlpha = 0.6;
        ctx2.lineWidth = 1;
        ctx2.stroke();
        ctx2.globalAlpha = 1;
        ctx2.fillStyle = ds.borderColor;
        ctx2.fillText(ds.label, px + 6, py + pillH - 5);
        ctx2.restore();
      });
    }
  };

  _compareChart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    plugins: [compareEndLabels],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      // v4 U6: without this the chart falls back to nearest+intersect:true and a
      // fingertip has to land on the 2.5px line itself. Same contract as the
      // scatter and timeline charts.
      interaction: { mode: 'nearest', intersect: false },
      scales: {
        x: {
          type: 'linear',
          reverse: true,
          title: { display: !_mobileVP(), text: 'Days Before Event', color: themeRgba(PALETTE.muted, 0.8), font: { size: 11 } },
          ticks: { color: themeRgba(PALETTE.muted, 0.6), font: { size: 11 }, maxTicksLimit: _mobileVP() ? 5 : 8, maxRotation: 0,
            callback(v) { return v === 0 ? 'Event' : v + 'd'; }
          },
          grid: { color: themeRgba(PALETTE.border, 0.4) }
        },
        y: {
          title: { display: !_mobileVP(), text: '% of Final Entries', color: themeRgba(PALETTE.muted, 0.8), font: { size: 11 } },
          ticks: { color: themeRgba(PALETTE.muted, 0.6), font: { size: 11 }, maxTicksLimit: _mobileVP() ? 5 : 8,
            callback(v) { return v + '%'; }
          },
          grid: { color: themeRgba(PALETTE.border, 0.4) },
          min: 0
        }
      },
      plugins: {
        legend: {
          display: true,
          labels: {
            color: PALETTE.text2,
            font: { size: 11 },
            boxWidth: _mobileVP() ? 8 : 12,
            padding: _mobileVP() ? 6 : 10,
            filter(item) { return !item.text.includes('· Today'); },
            usePointStyle: true, pointStyle: 'line'
          }
        },
        tooltip: {
          backgroundColor: themeRgba(PALETTE.surface, 0.95),
          borderColor: themeRgba(PALETTE.border, 0.8),
          borderWidth: 1,
          titleColor: PALETTE.text,
          bodyColor: PALETTE.text2,
          footerColor: PALETTE.muted,
          padding: 12,
          cornerRadius: 8,
          titleFont: { size: _mobileVP() ? 12 : 14, weight: 'bold' },
          bodyFont: { size: 12 },
          usePointStyle: true, pointStyleWidth: _mobileVP() ? 6 : 8,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              const db = items[0].parsed.x;
              return db === 0 ? 'Event Day' : `T-${db} (${db} days before)`;
            },
            label(item) {
              return ` ${item.dataset.label}: ${item.parsed.y.toFixed(1)}%`;
            }
          }
        }
      }
    }
  });
}
