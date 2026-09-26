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

const CACHE_NAME = 'cca-predictor-v84';

// The API routes the same Worker serves next to the site. Their responses are
// dynamic and must never enter the cache or be answered from it.
const API_ROUTE_RE = /^\/(ask|health|cca-tourlist|cca-entrylist)$/;

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
  'styles/fonts.css?v=d265109c48',
  'styles/tokens.css?v=56b8c4ba24',
  'styles/01-base.css?v=03f7525f8c',
  'styles/shell.css?v=963c55f4d6',
  'styles/controls.css?v=b613b1aa7d',
  'styles/overlays.css?v=f86784d8b1',
  'styles/picker.css?v=d1ecc80b37',
  'styles/03-cmdk.css?v=8be0b8a479',
  'styles/05-delta-banner.css?v=c417adc28d',
  'styles/06-mobile-predictions.css?v=2a44f6db76',
  'styles/07-hero.css?v=30b8537fa1',
  'styles/08-chart.css?v=c0add30020',
  'styles/09-timeline.css?v=10d9c06e16',
  'styles/10-comparison.css?v=95f4408fbe',
  'styles/11-tables.css?v=52afde408e',
  'styles/12-calendar.css?v=72c2b03dd8',
  'styles/cards.css?v=72fbc82335',
  'styles/14-puzzles.css?v=aa45d7e583',
  'styles/15-data-entry.css?v=c68b8317e2',
  'styles/16-email.css?v=774e6cca13',
  'styles/17-compare.css?v=33bdbebd97',
  'styles/18-performance.css?v=854b88f78f',
  'styles/19-motion.css?v=272bb138e5',
  'styles/20-mobile.css?v=68d5a1d54c',
  'styles/21-panels.css?v=8d1d4e15e7',
  'styles/22-panels-shared.css?v=e73fd9661f',
  'styles/23-print.css?v=ed72791308',
  'styles/24-ask-audit.css?v=62b5d908cd',
  'styles/theme.css?v=86ed0bd11f',
  'fonts/archivo/archivo-latin.woff2',
  'fonts/archivo/archivo-latin-ext.woff2',
  'fonts/courier-prime/courier-prime-400-latin.woff2',
  'fonts/courier-prime/courier-prime-400-latin-ext.woff2',
  'fonts/courier-prime/courier-prime-700-latin.woff2',
  'fonts/courier-prime/courier-prime-700-latin-ext.woff2',
  'theme.js?v=33c380c35b',
  'icons.js?v=eeee8884c1',
  'sheet.js?v=7c8a1ac5ef',
  'shell.js?v=75f177706e',
  'boot.js?v=cc39f2ee1b',
  'app.js?v=41adebf7d3',
  'actions.js?v=332edb1511',
  'audit.js?v=3da328f6fc',
  'daily_series.js?v=e326e2b1fc',
  'util_core.js?v=2824d286fc',
  'foundation.js?v=02d5d663f8',
  'cmdk.js?v=c497999f1f',
  'tab_email.js?v=09dda48c3a',
  'tab_performance.js?v=63e8c55dc2',
  'tab_puzzles.js?v=d37fdbb7f7',
  'pickers.js?v=fbcaedd103',
  'panels_info.js?v=85cb77359f',
  'hero_kpi.js?v=9347620d65',
  'chart_main.js?v=209e0a59c4',
  'chart_hist.js?v=6bdf6c4896',
  'panels_grid.js?v=dc54324367',
  'panels_cal.js?v=28d15e5f60',
  'tab_about.js?v=e7497b7332',
  'tab_compare.js?v=f99dade8a4',
  'tab_ask.js?v=ac0057506c',
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
  '<style>body{background:#FFFFFF;color:#111111;font-family:Archivo,system-ui,sans-serif;display:flex;' +
  'justify-content:center;align-items:center;height:100vh;margin:0;text-align:center}' +
  'h1{text-transform:uppercase}</style></head><body><div><h1>Offline</h1><p>CCA Entry Predictor is unavailable. ' +
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
  // Everything else cross-origin bypasses the worker, and so do the
  // same-origin API routes.
  if (url.origin !== self.location.origin) return;
  if (API_ROUTE_RE.test(url.pathname)) return;

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
