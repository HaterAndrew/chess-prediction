// foundation.js — theme palette, shared chart state, and the viewport,
// haptic, idle and escape helpers (split verbatim from app.js, C2). The
// chart range window and the house chart style are in chart_kit.js.

// ══════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════
// Opt out of browser scroll-restoration. With the mobile reorientation
// (round Path A) doing CSS-order shuffling, restored scroll positions from
// prior visits land users mid-page on reload. Always start fresh at top.
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

// Theme bridge: Chart.js configs and raw canvas code cannot resolve var(--x),
// so the tokens.css values are resolved into PALETTE. It is one mutable
// object, refilled by rebuildPalette() on a theme switch, so every file that
// captured the reference sees the new colours. Fallbacks mirror the dark
// palette in tokens.css; update both together.
//
// Tokens like --dim are color-mix() expressions, which getComputedStyle
// returns unresolved on a custom property. A probe element resolves each
// one to a real rgb() through its `color` property.
const PALETTE = {};

// Normalise a computed colour to '#rrggbb' (or 'rgba(r,g,b,a)' when it has
// alpha). Chromium serialises a color-mix() result as 'color(srgb r g b)',
// which Chart.js's own colour parser does not read; canvas gradients and
// themeRgba() both want plain rgb.
function normalizeColor(c) {
  if (!c) return c;
  let m = /^color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\)$/.exec(c);
  if (m) {
    const [r, g, b] = [m[1], m[2], m[3]].map(v => Math.round(parseFloat(v) * 255));
    const a = m[4] === undefined ? 1 : parseFloat(m[4]);
    return a >= 1 ? '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
                  : `rgba(${r},${g},${b},${a})`;
  }
  m = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/.exec(c);
  if (m) {
    const [r, g, b] = [m[1], m[2], m[3]].map(v => Math.round(parseFloat(v)));
    let a = m[4] === undefined ? 1 : parseFloat(m[4]);
    if (m[4] && m[4].endsWith('%')) a = a / 100;
    return a >= 1 ? '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
                  : `rgba(${r},${g},${b},${a})`;
  }
  return c;
}

function readPalette() {
  const root = document.documentElement;
  const cs = getComputedStyle(root);
  const probe = document.createElement('span');
  probe.style.display = 'none';
  root.appendChild(probe);
  const t = (name, fb) => {
    const raw = (cs.getPropertyValue(name) || '').trim();
    if (!raw) return fb;
    probe.style.color = '';
    probe.style.color = raw;
    const resolved = getComputedStyle(probe).color;
    return normalizeColor(resolved && resolved !== 'rgba(0, 0, 0, 0)' ? resolved : raw);
  };
  const font = (name, fb) => (cs.getPropertyValue(name) || '').trim() || fb;
  const p = {
    // surfaces and ink (tokens.css "semantic roles")
    bg: t('--void', '#151517'),
    surface: t('--panel', '#151517'),
    surface2: t('--raised', '#1F1F23'),
    border: t('--line', '#8F8F8E'),
    text: t('--ink', '#F2F2EF'),
    text2: t('--ink-2', '#D4D4CF'),
    muted: t('--muted', '#A7A7A3'),
    // the two pens and the highlighter, for state drawn on canvas
    blue: t('--blue', '#8FB4F0'),
    red: t('--ember', '#FF7A8A'),
    mark: t('--mark', '#FFE94D'),
    markInk: t('--mark-ink', '#151517'),
    // chart roles (tokens.css "chart roles")
    actual: t('--chart-actual', '#8FB4F0'),
    projected: t('--chart-projected', '#F2F2EF'),
    band: t('--chart-band', 'rgba(143,180,240,.14)'),
    hist: t('--chart-hist', '#8A8A86'),
    grid: t('--chart-grid', '#2E2E32'),
    tick: t('--chart-tick', '#A7A7A3'),
    markerToday: t('--marker-today', '#F2F2EF'),
    markerEarly: t('--marker-early', '#8FB4F0'),
    markerEvent: t('--marker-event', '#FF7A8A'),
    series: [t('--series-1', '#8FB4F0'), t('--series-2', '#FF7A8A'), t('--series-3', '#F2F2EF')],
    fontDisplay: font('--display', "'Archivo', system-ui, sans-serif"),
    fontMono: font('--mono', "'Courier Prime', monospace")
  };
  probe.remove();
  return p;
}
function rebuildPalette() {
  Object.assign(PALETTE, readPalette());
}
rebuildPalette();

// rgba() string from a resolved token colour (hex or rgb()/rgba()), for chart
// grids and tooltips.
function themeRgba(color, alpha) {
  const m = /^rgba?\(([^)]+)\)$/.exec(color);
  if (m) {
    const [r, g, b] = m[1].split(',').map(s => parseFloat(s));
    return `rgba(${r},${g},${b},${alpha})`;
  }
  const n = color.replace('#', '');
  const h = n.length === 3 ? n.split('').map(c => c + c).join('') : n;
  return `rgba(${parseInt(h.slice(0,2),16)},${parseInt(h.slice(2,4),16)},${parseInt(h.slice(4,6),16)},${alpha})`;
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
// One MediaQueryList, read on every call: matchMedia builds a new list each
// time, and the chart's hit-testing and plugins ask per point and per frame.
const _MOBILE_MQ = window.matchMedia('(max-width: 639px)');
function _mobileVP() { return _MOBILE_MQ.matches; }
function _reduceMotion() {
  return typeof window !== 'undefined' && window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}
// Global animation kill under reduced motion, at top level so every chart is
// covered regardless of which tab renders first (a #performance deep link
// never runs renderChart). Every app script is `defer` and chart.umd.min.js
// is deferred earlier in the document, so Chart exists here; the typeof
// guard keeps a CDN failure from cascading. (Until 2026-09 the app scripts
// were classic, Chart was undefined at this point, and this block was dead.)
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
// Work that no visitor is waiting for (the tournament table below the fold,
// the About tab's telemetry) runs when the main thread is free, with a
// ceiling so it still lands on a busy phone. setTimeout is the fallback for
// Safari, which has no requestIdleCallback.
function _idle(fn, timeout) {
  if (typeof requestIdleCallback === 'function') {
    return requestIdleCallback(fn, { timeout: timeout || 1500 });
  }
  return setTimeout(fn, 0);
}
// The fold has rendered: the loading reservations (forecast.css, shell.css
// under html[data-loading]) and any placeholder blocks come off.
function hideSkeletons() {
  document.documentElement.removeAttribute('data-loading');
  document.querySelectorAll('.skeleton').forEach(el => el.style.display = 'none');
}

function esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

// Data files the page does not need at first paint (performance_data.js)
// ride the data tag as data-* attributes, so the pipeline
// stamps their ?v= alongside the page's own. Each is inserted once, on
// demand, as a same-origin classic script (CSP 'self'); the promise is cached
// so repeat callers share one request, and dropped on failure so the next
// visit to the tab retries instead of failing forever.
const _dataFileLoads = {};
function loadDataFile(key) {
  if (_dataFileLoads[key]) return _dataFileLoads[key];
  const tag = document.getElementById('dataScript');
  const src = tag && tag.dataset[key];
  if (!src) return Promise.reject(new Error(`no data file registered for "${key}"`));
  _dataFileLoads[key] = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = () => resolve(src);
    s.onerror = () => {
      delete _dataFileLoads[key];
      reject(new Error(`failed to load ${src}`));
    };
    document.head.appendChild(s);
  });
  return _dataFileLoads[key];
}
