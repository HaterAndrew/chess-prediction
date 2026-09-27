// chart_kit.js — the house chart style every canvas shares, the main chart's
// range window, and the marker-pill plugin (moved from foundation.js).
//
// The style follows DESIGN.md § Charts: horizontal grid in the faint rule
// only, ticks in muted Archivo at 11px, figures in Courier Prime, square
// tooltips on the sheet. Each chart takes these helpers instead of copying
// the values, so a token change reaches every canvas.

// ══════════════════════════════════════════════════════════
// HOUSE STYLE
// ══════════════════════════════════════════════════════════
// The value axis: faint horizontal lines to read a value against, no axis
// rule. extra merges over the defaults (a chart that needs the zero line
// drawn passes its own border).
function chartGridY(extra) {
  return Object.assign({ color: PALETTE.grid, drawTicks: false }, extra);
}
// The category or time axis: no vertical grid; its rule is the baseline.
function chartGridX() {
  return { display: false };
}
function chartBorderX() {
  return { display: true, color: PALETTE.border, width: 1 };
}
function chartBorderY() {
  return { display: false };
}
// Tick labels: muted at full strength (the 60% tint read 2.75:1), 11px.
function chartTicks(extra) {
  return Object.assign({
    color: PALETTE.muted,
    font: { family: PALETTE.fontDisplay, size: 11 },
    maxRotation: 0,
    padding: 6,
  }, extra);
}
// An axis title; phones drop it for the plot's width.
function chartAxisTitle(text) {
  return { display: !_mobileVP(), text, color: PALETTE.muted, font: { family: PALETTE.fontDisplay, size: 11 } };
}
// Canvas text for figures drawn by a plugin: Courier Prime, 12px unless
// asked otherwise, never under 11px.
function chartLabelFont(size, weight) {
  const px = Math.max(11, size || 12);
  return `${weight ? weight + ' ' : ''}${px}px ${PALETTE.fontMono}`;
}
// The square sheet tooltip. extra merges over it (callbacks, filters).
function chartTooltip(extra) {
  return Object.assign({
    backgroundColor: themeRgba(PALETTE.surface, 0.95),
    borderColor: themeRgba(PALETTE.border, 0.8), borderWidth: 1,
    titleColor: PALETTE.text, bodyColor: PALETTE.text2, footerColor: PALETTE.muted,
    padding: 12, cornerRadius: 0,
    titleFont: { size: _mobileVP() ? 12 : 14, weight: 'bold' },
    bodyFont: { size: 12 }, footerFont: { size: 11, style: 'italic' },
  }, extra);
}

// The chart's text alternative (W3C WAI, complex images): a short label on
// the canvas that states the figures, and its data as a table only screen
// readers reach. spec: { label, caption, columns, rows }; chartTableHTML
// (chart_data.js) escapes every cell.
function chartDescribe(canvas, spec) {
  if (!canvas) return;
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', spec.label || '');
  const id = (canvas.id || 'chart') + 'Data';
  let table = document.getElementById(id);
  if (!spec.rows || !spec.rows.length) {
    if (table) table.remove();
    return;
  }
  if (!table) {
    table = document.createElement('table');
    table.id = id;
    table.className = 'sr-only';
    canvas.insertAdjacentElement('afterend', table);
  }
  table.innerHTML = chartTableHTML(spec);
}

// A chart built at one width keeps that width's options (the past years
// drawn, tick density, label placement). Crossing the phone breakpoint
// redraws the charts on screen and marks the rest stale (theme.js).
if (typeof _MOBILE_MQ.addEventListener === 'function') {
  _MOBILE_MQ.addEventListener('change', () => {
    if (typeof refreshCharts === 'function') refreshCharts();
  });
}

// ══════════════════════════════════════════════════════════
// MAIN CHART RANGE
// ══════════════════════════════════════════════════════════
// Chart range preference: one global choice, per-tournament validity decides
// whether it can apply (see _chartWindow).
const CHART_RANGE_KEY = 'cca_chartRange';
function _getStoredChartRange() {
  try { return localStorage.getItem(CHART_RANGE_KEY) || ''; } catch (e) { return ''; }
}
function _storeChartRange(key) {
  try { localStorage.setItem(CHART_RANGE_KEY, key); } catch (e) {}
}
let _chartWindowState = null;   // { t, series, dayToDate } of the rendered chart

// Resolve the visible x-window for the main chart. A window (90d/30d before
// event) is valid only when it trims real flat head AND still contains the
// tail of the actual data; otherwise it would render an empty line (far-future
// tournaments have no points inside 90d). forceKey: user request via the
// segmented control; 'all' is always valid.
function _chartWindow(t, series, dayToDate, forceKey) {
  const out = { key: 'all', min: undefined, max: undefined, valid90: false, valid30: false };
  if (!t.event_start || !series.length) return out;
  const msDay = 86400000;
  const dataStart = dayToDate(series[0][0]);
  const lastActual = dayToDate(series[series.length - 1][0]);
  const eventDate = new Date(t.event_start + 'T00:00:00');
  const winStart = w => new Date(eventDate.getTime() - w * msDay);
  out.valid90 = winStart(90) > dataStart && lastActual >= winStart(90);
  out.valid30 = winStart(30) > dataStart && lastActual >= winStart(30);

  let key = forceKey || _getStoredChartRange();
  if (key === '90' && !out.valid90) key = '';
  if (key === '30' && !out.valid30) key = out.valid90 ? '90' : '';
  if (key !== 'all' && key !== '90' && key !== '30') key = '';
  if (!key) {
    // Smart default: if the sub-10%-of-final flat head eats more than half the
    // span, open on the 90d window instead of the full flatline.
    const FLAT_PCT = 0.1, FLAT_SPAN = 0.5;
    const finalCum = series[series.length - 1][1];
    let flatEnd = dataStart;
    for (const pt of series) {
      if (pt[1] >= finalCum * FLAT_PCT) { flatEnd = dayToDate(pt[0]); break; }
    }
    const flatFrac = (flatEnd - dataStart) / Math.max(1, eventDate - dataStart);
    key = (flatFrac > FLAT_SPAN && out.valid90) ? '90' : 'all';
  }
  out.key = key;

  const visStart = key === 'all' ? dataStart : winStart(Number(key));
  const visSpan = Math.max(1, Math.round((eventDate - visStart) / msDay));
  out.max = addDays(t.event_start, Math.max(5, Math.round(0.08 * visSpan)));
  if (key !== 'all') out.min = winStart(Number(key));
  return out;
}

// Time-scale unit for the chosen window: a 30d window with month labels shows
// one or two ticks, so anything at or under 45d gets weekly ticks everywhere.
function _chartTimeUnit(cw, t) {
  const winDays = cw.min ? Math.round((new Date(t.event_start + 'T00:00:00') - cw.min) / 86400000) : null;
  if (winDays && winDays <= 45) return { unit: 'week', displayFormats: { week: 'MMM d' } };
  return _mobileVP()
    ? { unit: 'month', displayFormats: { month: 'MMM' } }
    : { unit: 'week', displayFormats: { week: 'MMM d' } };
}

function _syncChartRangeSeg(cw) {
  const seg = document.getElementById('chartRangeSeg');
  if (!seg) return;
  seg.querySelectorAll('button').forEach(b => {
    const r = b.dataset.range;
    b.classList.toggle('active', r === cw.key);
    b.disabled = !(r === 'all' || (r === '90' ? cw.valid90 : cw.valid30));
  });
}

function setChartRange(key) {
  const st = _chartWindowState;
  if (!chart || !st) return;
  const cw = _chartWindow(st.t, st.series, st.dayToDate, key);
  if (cw.key !== key) return;   // requested window not valid here
  _storeChartRange(key);
  chart.options.scales.x.min = cw.min;
  chart.options.scales.x.max = cw.max;
  chart.options.scales.x.time = _chartTimeUnit(cw, st.t);
  // 'none': a default-mode update() replays the progressive draw-in from a
  // blank line on every range click (the resize handler already does this).
  chart.update('none');
  _syncChartRangeSeg(cw);
}

// Shared vertical-marker plugin factory: dashed line + clamped, row-stacked
// pill label at the top of the plot area. getMarkers(chartInstance) returns
// [{ value, label, color }] where value is whatever the chart's x scale
// resolves — a Date on time scales (main chart), an index on category scales
// (registration curve).
//
// A label's width is measured once per font: measureText shapes the text
// through the web font on every call, and the plugin draws on every
// animation frame. The cache empties when the fonts finish loading, since
// a width measured against the fallback face is wrong afterwards.
const _labelWidths = new Map();
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => _labelWidths.clear());
function _labelWidth(ctx2, label) {
  const key = ctx2.font + '|' + label;
  let w = _labelWidths.get(key);
  if (w === undefined) {
    w = ctx2.measureText(label).width;
    _labelWidths.set(key, w);
  }
  return w;
}
function makeVertMarkersPlugin(id, getMarkers) {
  return {
    id,
    afterDraw(chartInstance) {
      const ctx2 = chartInstance.ctx;
      const xScale = chartInstance.scales.x;
      const yScale = chartInstance.scales.y;
      const lines = getMarkers(chartInstance) || [];

      // One size on every width: a 9px pill on a phone was the smallest text
      // on the page (DESIGN.md's floor is 11px).
      const annoFont = 'bold 11px';
      const pillH = 16;
      const pillYOff = 18;
      const textYOff = 6;
      const rowGap = 3;
      // Track drawn pill bounding boxes so a new pill that horizontally
      // overlaps any drawn pill stacks onto a higher row instead of
      // colliding (e.g. Early Bird + Event when their dates are 3 days
      // apart — pills are ~60-70px wide so they always overlap).
      const drawn = [];
      lines.forEach(line => {
        const x = xScale.getPixelForValue(line.value);
        if (x < xScale.left || x > xScale.right) return;
        ctx2.save();
        ctx2.beginPath();
        ctx2.setLineDash([4, 4]);
        ctx2.strokeStyle = line.color;
        ctx2.globalAlpha = 0.7;
        ctx2.lineWidth = 1;
        ctx2.moveTo(x, yScale.top);
        ctx2.lineTo(x, yScale.bottom);
        ctx2.stroke();
        ctx2.setLineDash([]);
        ctx2.globalAlpha = 1;
        ctx2.font = `${annoFont} ${PALETTE.fontMono}`;
        ctx2.textAlign = 'center';
        const textW = _labelWidth(ctx2, line.label);
        const pillW = textW + 10;
        // Clamp pill horizontally so it never spills past the chart area.
        // Right-edge clipping was visible on tournaments where the Event
        // line sits at the far right of the extended axis.
        let pillX = x - textW / 2 - 5;
        if (pillX + pillW > xScale.right) pillX = xScale.right - pillW;
        if (pillX < xScale.left) pillX = xScale.left;
        // Pick a vertical row that doesn't horizontally overlap a drawn
        // pill. Row 0 = original Y; row N stacks upward by pillH + gap.
        let row = 0;
        while (drawn.some(d => d.row === row &&
                                !(pillX + pillW < d.x || pillX > d.x2))) {
          row++;
        }
        const pillY = yScale.top - pillYOff - row * (pillH + rowGap);
        drawn.push({ x: pillX, x2: pillX + pillW, row });
        ctx2.fillStyle = themeRgba(PALETTE.surface, 0.85);
        ctx2.beginPath();
        ctx2.rect(pillX, pillY, pillW, pillH);
        ctx2.fill();
        ctx2.strokeStyle = line.color;
        ctx2.lineWidth = 1;
        ctx2.globalAlpha = 0.6;
        ctx2.stroke();
        ctx2.globalAlpha = 1;
        // Draw label text centered on the pill (not on the line) so the
        // clamp + stack stay legible.
        ctx2.fillStyle = line.color;
        ctx2.fillText(line.label, pillX + pillW / 2, pillY + pillH - textYOff);
        ctx2.restore();
      });
    }
  };
}
