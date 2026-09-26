// Service worker: the browser's rule for what may come from cache.
//
// The document is always fetched fresh (network-first, no-store): it carries
// every asset's `?v=` pointer, so it is the one thing that must never be
// stale. Everything referenced with a content hash (`?v=`) and the font files
// are immutable by construction, so they are served cache-first, and a new
// hash evicts the old entry for the same path. Unhashed same-origin files
// (audit_warnings.json, manifest.json, icons) stay network-first with the
// cache as the offline fallback. Cross-origin requests bypass the worker,
// except the pinned, SRI-locked CDN scripts, which are cache-first too.
//
// CACHE_NAME is bumped on every deploy that reshapes caching behaviour so
// caches from prior worker versions are purged on activate.

const CACHE_NAME = 'cca-predictor-v80';

// Version-pinned, SRI-locked CDN scripts. Immutable, so cache-first. This is
// also the runtime allowlist for the on-demand ExcelJS load in audit.js.
const CDN_ASSETS = [
  'https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js',
  'https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/exceljs@4.4.0/dist/exceljs.min.js'
];

// The app shell, precached at install so an offline return visit still boots.
// The data file is not listed: it is a `?v=` URL, cached on first use by the
// fetch handler, and precaching 2.4 MB during the first visit competed with
// the page's own requests. The CDN scripts are cached the same way.
const OFFLINE_FALLBACKS = [
  './',
  'index.html',
  'styles/fonts.css?v=2bc8c06a4c',
  'styles/tokens.css?v=3077da881d',
  'styles/01-base.css?v=73b0c0c377',
  'styles/02-header.css?v=b5bce10024',
  'styles/03-cmdk.css?v=3495a63afb',
  'styles/04-tab-bar.css?v=207983e2a3',
  'styles/05-delta-banner.css?v=c417adc28d',
  'styles/06-mobile-predictions.css?v=f4343ee607',
  'styles/07-hero.css?v=30b8537fa1',
  'styles/08-chart.css?v=5db35ae41c',
  'styles/09-timeline.css?v=10d9c06e16',
  'styles/10-comparison.css?v=95f4408fbe',
  'styles/11-tables.css?v=f202f61be5',
  'styles/12-calendar.css?v=72c2b03dd8',
  'styles/13-page-tabs.css?v=fe452df7e7',
  'styles/14-puzzles.css?v=aa45d7e583',
  'styles/15-data-entry.css?v=320069fa4b',
  'styles/16-email.css?v=774e6cca13',
  'styles/17-compare.css?v=fcf1e5b883',
  'styles/18-performance.css?v=3021f4f852',
  'styles/19-motion.css?v=c03cb6462f',
  'styles/20-mobile.css?v=4f98c62cf1',
  'styles/21-panels.css?v=ff65e05713',
  'styles/22-panels-shared.css?v=f9c76fe03a',
  'styles/23-print.css?v=8eacb65c69',
  'styles/24-ask-audit.css?v=62b5d908cd',
  'styles/theme.css?v=0279f37cbc',
  'fonts/ibm-plex-mono/plex-mono-400-latin-ext.woff2',
  'fonts/ibm-plex-mono/plex-mono-400-latin.woff2',
  'fonts/ibm-plex-mono/plex-mono-500-latin-ext.woff2',
  'fonts/ibm-plex-mono/plex-mono-500-latin.woff2',
  'fonts/ibm-plex-mono/plex-mono-600-latin-ext.woff2',
  'fonts/ibm-plex-mono/plex-mono-600-latin.woff2',
  'fonts/inter/inter-latin-ext.woff2',
  'fonts/inter/inter-latin.woff2',
  'theme.js?v=33c380c35b',
  'boot.js?v=b9c1bc6557',
  'app.js?v=612241529c',
  'actions.js?v=a953337851',
  'audit.js?v=c8288fbf68',
  'daily_series.js?v=e326e2b1fc',
  'util_core.js?v=2824d286fc',
  'foundation.js?v=8702a837a3',
  'cmdk.js?v=c497999f1f',
  'tab_email.js?v=09dda48c3a',
  'tab_performance.js?v=f7b2bf4982',
  'tab_puzzles.js?v=c0b01b5c3e',
  'pickers.js?v=00fe32ddb5',
  'panels_info.js?v=85cb77359f',
  'hero_kpi.js?v=c32d542fd4',
  'chart_main.js?v=209e0a59c4',
  'chart_hist.js?v=6bdf6c4896',
  'panels_grid.js?v=328099e6c3',
  'panels_cal.js?v=28d15e5f60',
  'tab_about.js?v=93bd7709b3',
  'tab_compare.js?v=c14237e866',
  'tab_ask.js?v=07df7455b0',
  'manifest.json',
  'icons/icon-192.png'
];

// The document and its alias are fetched no-cache at install so the precached
// copy is the current deploy, not whatever the HTTP cache held. Every other
// entry was just fetched by the page that registered this worker, so the
// default cache mode makes those precache reads free.
const FRESH_AT_INSTALL = new Set(['./', 'index.html']);

const OFFLINE_PAGE =
  '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Offline</title>' +
  '<style>body{background:#F7F4EC;color:#28241B;font-family:Inter,system-ui,sans-serif;display:flex;' +
  'justify-content:center;align-items:center;height:100vh;margin:0;text-align:center}' +
  'h1{color:#9A7010}</style></head><body><div><h1>Offline</h1><p>CCA Entry Predictor is unavailable. ' +
  'Check your connection and try again.</p></div></body></html>';

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.all(
        OFFLINE_FALLBACKS.map(url =>
          fetch(url, FRESH_AT_INSTALL.has(url) ? { cache: 'no-cache' } : undefined)
            .then(resp => resp.ok ? cache.put(url, resp) : null)
            .catch(() => null)
        )
      )
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Immutable by construction: a `?v=` URL changes when its content does, and
// the font files are fixed subsets that only ever change with their path.
function isImmutable(url) {
  return url.searchParams.has('v') || url.pathname.includes('/fonts/');
}

// Store the response and evict every other version of the same path, so a
// nightly restamp of the data file does not leave yesterday's copy behind.
function putAndPrune(request, response) {
  return caches.open(CACHE_NAME).then(cache =>
    cache.keys(request, { ignoreSearch: true })
      .then(stale => Promise.all(
        stale.filter(r => r.url !== request.url).map(r => cache.delete(r))))
      .then(() => cache.put(request, response)));
}

function cacheFirst(request) {
  return caches.match(request).then(cached => {
    if (cached) return cached;
    return fetch(request).then(response => {
      if (response && (response.ok || response.type === 'opaque')) {
        putAndPrune(request, response.clone());
      }
      return response;
    });
  }).catch(() => new Response('', { status: 504 }));
}

function networkFirst(request) {
  return fetch(request)
    .then(response => {
      if (response && response.ok && response.type !== 'opaque') {
        caches.open(CACHE_NAME).then(cache => cache.put(request, response.clone()));
      }
      return response;
    })
    .catch(() => caches.match(request))
    .then(response => response || new Response('', { status: 504 }));
}

// The document carries every asset's `?v=` pointer, so it is fetched with
// no-store: Pages serves it with `max-age=600`, and inside that window the
// HTTP cache would hand a returning visitor a document that still points at
// the previous data URL, which made the cache-busting do nothing for exactly
// the visitor it exists to protect.
function navigation(request) {
  return fetch(request, { cache: 'no-store' })
    .then(response => {
      if (response && response.ok) {
        caches.open(CACHE_NAME).then(cache => cache.put(request, response.clone()));
      }
      return response;
    })
    .catch(() => caches.match(request))
    .then(response => response || new Response(OFFLINE_PAGE, {
      status: 503, headers: { 'Content-Type': 'text/html' }
    }));
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  if (CDN_ASSETS.includes(url.href)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  // Everything else cross-origin (the Ask Worker) bypasses the worker.
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(navigation(request));
    return;
  }
  if (isImmutable(url)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  event.respondWith(networkFirst(request));
});
