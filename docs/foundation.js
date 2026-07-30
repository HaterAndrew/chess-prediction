// foundation.js — theme palette, shared chart state, viewport/haptic/esc
// helpers, chart-range window machinery, marker-pill plugin factory and
// the injected chart-highlight style, split verbatim from app.js (C2).

// ══════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════
// Opt out of browser scroll-restoration. With the mobile reorientation
// (round Path A) doing CSS-order shuffling, restored scroll positions from
// prior visits land users mid-page on reload. Always start fresh at top.
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

// Theme bridge: Chart.js configs and raw canvas code cannot resolve var(--x),
// so resolve the styles.css :root tokens once at startup. Fallbacks mirror
// the :root values; update both together (Phase 3 retint, 2026-07).
const PALETTE = (() => {
  const cs = getComputedStyle(document.documentElement);
  const t = (name, fb) => (cs.getPropertyValue(name) || '').trim() || fb;
  return {
    bg: t('--bg', '#0a0907'),
    surface: t('--surface', '#12100d'),
    surface2: t('--surface2', '#1d1a17'),
    surface3: t('--surface3', '#282521'),
    border: t('--border', '#383530'),
    text: t('--text', '#eeece8'),
    text2: t('--text2', '#d2cfcb'),
    muted: t('--muted', '#96928c'),
    blue: t('--blue', '#58a6ff'),
    blueBright: t('--blue-bright', '#79c0ff'),
    gold: t('--gold', '#f0c040'),
    goldBright: t('--gold-bright', '#f7d970'),
    green: t('--green', '#3fb950'),
    greenBright: t('--green-bright', '#56d364'),
    red: t('--red', '#f85149'),
    orange: t('--orange', '#d29922'),
    orangeBright: t('--orange-bright', '#f59e0b')
  };
})();

// rgba() string from a resolved token hex, for chart grids and tooltips.
function themeRgba(hex, alpha) {
  const n = hex.replace('#', '');
  const h = n.length === 3 ? n.split('').map(c => c + c).join('') : n;
  return `rgba(${parseInt(h.slice(0,2),16)},${parseInt(h.slice(2,4),16)},${parseInt(h.slice(4,6),16)},${alpha})`;
}

// Vertical gradient for scriptable backgroundColor, cached per chart area.
// Chart.js resolves scriptable colors once before layout, when chartArea is
// still undefined — return the bottom stop as a flat fallback for that pass.
// The cache object is supplied by the call site (one per dataset) and keyed
// on the chart-area extent so resize rebuilds the CanvasGradient exactly once
// instead of allocating a new one on every scriptable resolution.
function areaGradient(chart2, cache, stops) {
  const { ctx, chartArea } = chart2;
  if (!chartArea) return stops[stops.length - 1][1];
  const key = chartArea.top + ':' + chartArea.bottom;
  if (cache.key !== key) {
    const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
    stops.forEach(([at, color]) => g.addColorStop(at, color));
    cache.key = key;
    cache.grad = g;
  }
  return cache.grad;
}
let selectedIndex = 0;
let chart = null;
let histChartObj = null;
let perfScatterChart = null;
let perfTimelineChart = null;
// (dropdownOpen removed — using openDrop from tab bar system)

// ══════════════════════════════════════════════════════════
// HELPERS
// ══════════════════════════════════════════════════════════
function _mobileVP() { return window.matchMedia('(max-width: 639px)').matches; }
function _reduceMotion() {
  return typeof window !== 'undefined' && window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}
// Global animation kill under reduced motion, at top level so every chart is
// covered regardless of which tab renders first (a #performance deep link
// never runs renderChart). app.js is deferred after chart.umd.min.js, so
// Chart exists here; the typeof guard keeps a CDN failure from cascading.
// v4 U4: also track mid-session OS toggles. Existing chart instances keep
// their config until their next render (every tab switch re-renders), but the
// default flips immediately for anything created after the change.
if (typeof Chart !== 'undefined' && typeof window !== 'undefined' && window.matchMedia) {
  const _rmQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const _animDefault = Chart.defaults.animation;
  if (_rmQuery.matches) Chart.defaults.animation = false;
  if (typeof _rmQuery.addEventListener === 'function') {
    _rmQuery.addEventListener('change', () => {
      Chart.defaults.animation = _rmQuery.matches ? false : _animDefault;
    });
  }
}
// Progressive-enhancement haptic. Android Chrome/Firefox supported; iOS Safari
// no-ops. Respects prefers-reduced-motion. Round 31.
function _haptic(ms) {
  if (typeof navigator === 'undefined' || !navigator.vibrate) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  try { navigator.vibrate(ms || 12); } catch (_) {}
}
function hideSkeletons() {
  document.querySelectorAll('.skeleton').forEach(el => el.style.display = 'none');
  const loader = document.getElementById('skeletonLoader');
  if (loader) loader.style.display = 'none';
}

function esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

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

// Re-apply mobile-aware chart options on viewport change (orientation flip,
// devtools emulation toggle, browser resize). Without this, charts initialized
// at one viewport keep their original tick density / time unit even after
// the layout crosses the 640px breakpoint.
let _chartResizeT;
window.addEventListener('resize', () => {
  clearTimeout(_chartResizeT);
  _chartResizeT = setTimeout(() => {
    const isM = _mobileVP();
    if (chart && chart.options && chart.options.scales) {
      const xs = chart.options.scales.x;
      const ys = chart.options.scales.y;
      if (xs && xs.time) {
        xs.time.unit = isM ? 'month' : 'week';
        xs.time.displayFormats = isM ? { month: 'MMM' } : { week: 'MMM d' };
      }
      if (xs && xs.ticks) xs.ticks.font = { size: isM ? 10 : 11 };
      if (ys && ys.ticks) {
        ys.ticks.font = { size: isM ? 10 : 11 };
        ys.ticks.maxTicksLimit = isM ? 4 : 8;
      }
      chart.update('none');
    }
  }, 200);
});

// ══════════════════════════════════════════════════════════
// CHART
// ══════════════════════════════════════════════════════════
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
function makeVertMarkersPlugin(id, getMarkers) {
  return {
    id,
    afterDraw(chartInstance) {
      const ctx2 = chartInstance.ctx;
      const xScale = chartInstance.scales.x;
      const yScale = chartInstance.scales.y;
      const lines = getMarkers(chartInstance) || [];

      const isMobile = _mobileVP();
      const annoFont = isMobile ? 'bold 9px' : 'bold 11px';
      const pillH = isMobile ? 14 : 16;
      const pillYOff = isMobile ? 16 : 18;
      const textYOff = isMobile ? 5 : 6;
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
        ctx2.font = `${annoFont} -apple-system, system-ui, sans-serif`;
        ctx2.textAlign = 'center';
        const textW = ctx2.measureText(line.label).width;
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
        ctx2.roundRect(pillX, pillY, pillW, pillH, 4);
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

// ══════════════════════════════════════════════════════════
// CHART-HIGHLIGHT STYLE (injected for click-to-table feature)
// ══════════════════════════════════════════════════════════
(function() {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes chartHighlightPulse {
      0% { background-color: rgba(240,192,64,0.25); }
      100% { background-color: transparent; }
    }
    .chart-highlight {
      animation: chartHighlightPulse 2.5s ease-out forwards;
      outline: 1px solid rgba(240,192,64,0.4);
      outline-offset: -1px;
    }
  `;
  document.head.appendChild(style);
})();
