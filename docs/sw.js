// Service worker: the browser's rule for what may come from cache.
//
// The document is always fetched fresh (network-first, no-store): it carries
// every asset's `?v=` pointer, so it is the one thing that must never be
// stale. Everything referenced with a content hash (`?v=`) and the font files
// are immutable by construction, so they are served cache-first, and a new
// hash evicts the old entry for the same path. Unhashed same-origin files
// (audit_warnings.json, manifest.json, icons) stay network-first with the
// cache as the offline fallback. Cross-origin requests bypass the worker,
// except the pinned, SRI-locked CDN script, which is cache-first too.
//
// CACHE_NAME is bumped on every deploy that reshapes caching behaviour so
// caches from prior worker versions are purged on activate.

const CACHE_NAME = 'cca-predictor-v85';

// The API routes the same Worker serves next to the site. Their responses are
// dynamic and must never enter the cache or be answered from it.
const API_ROUTE_RE = /^\/(ask|health|cca-tourlist|cca-entrylist)$/;

// Version-pinned, SRI-locked CDN scripts. Immutable, so cache-first. This is
// the runtime allowlist for the on-demand ExcelJS load in audit.js; the
// chart library is served from this origin (vendor/) and precached below.
const CDN_ASSETS = [
  'https://cdn.jsdelivr.net/npm/exceljs@4.4.0/dist/exceljs.min.js'
];

// The app shell, precached at install so an offline return visit still boots:
// the document, the stylesheet and script bundles, the chart library, the
// fonts. The data file is not listed: it is a `?v=` URL, cached on first use
// by the fetch handler, and precaching 2.4 MB during the first visit competed
// with the page's own requests. The CDN script is cached the same way.
const OFFLINE_FALLBACKS = [
  './',
  'index.html',
  'styles/site.css?v=df95681741',
  'fonts/archivo/archivo-latin.woff2',
  'fonts/archivo/archivo-latin-ext.woff2',
  'fonts/courier-prime/courier-prime-400-latin.woff2',
  'fonts/courier-prime/courier-prime-400-latin-ext.woff2',
  'fonts/courier-prime/courier-prime-700-latin.woff2',
  'fonts/courier-prime/courier-prime-700-latin-ext.woff2',
  'boot.js?v=cc39f2ee1b',
  'vendor/chart.umd.min.js?v=48444a82d4',
  'vendor/chartjs-adapter-date-fns.bundle.min.js?v=ea7ab30d26',
  'site.js?v=4baa410689',
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
