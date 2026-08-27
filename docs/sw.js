// Network-first service worker. Always fetch fresh when online so deploys
// show immediately; fall back to cache only when offline.
// Cache name is bumped on each deploy that reshapes caching behavior so
// old caches from prior SW versions get purged on activate.

const CACHE_NAME = 'cca-predictor-v78';

// Version-pinned, SRI-locked CDN scripts. Immutable, so serve them cache-first
// (see the fetch handler) instead of letting the cross-origin bypass drop them
// — that bypass meant a repeat/offline load got "Chart is not defined".
const CDN_ASSETS = [
  'https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js',
  'https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/exceljs@4.4.0/dist/exceljs.min.js'
];

const OFFLINE_FALLBACKS = [
  './',
  'index.html',
  'styles.css?v=96f245ba47',
  'boot.js?v=ccde1eb234',
  'app.js?v=9c09a86d56',
  'actions.js?v=886915259e',
  'audit.js?v=30eaa762a6',
  'daily_series.js?v=e326e2b1fc',
  'util_core.js?v=2824d286fc',
  'foundation.js?v=4d4e27e30b',
  'cmdk.js?v=c497999f1f',
  'tab_email.js?v=62b9000739',
  'tab_performance.js?v=e9814abef3',
  'tab_puzzles.js?v=c0b01b5c3e',
  'pickers.js?v=00fe32ddb5',
  'panels_info.js?v=85cb77359f',
  'hero_kpi.js?v=b50035a2fc',
  'chart_main.js?v=14f63c8b82',
  'chart_hist.js?v=df0ad1a8e2',
  'panels_grid.js?v=b50a890ae4',
  'panels_cal.js?v=28d15e5f60',
  'tab_about.js?v=1a12f01317',
  'tab_compare.js?v=fa214e72e7',
  'tab_ask.js?v=07df7455b0',
  'data/site_data.js?v=e30075898a',
  // v4 W4: Model Health fetches this at runtime; without a precached copy an
  // offline load 504s and the panel renders empty.
  'audit_warnings.json',
  'manifest.json',
  'icons/icon-192.png',
  ...CDN_ASSETS
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.all(
        OFFLINE_FALLBACKS.map(url =>
          fetch(url, { cache: 'no-cache' })
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

// Fetch: network-first for same-origin GETs only. Never intercept cross-origin
// requests (the Ask Worker lives at chess-ask.workers.dev and must bypass the
// SW entirely) and never intercept non-GET methods.
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);

  // Cache-first for the pinned CDN chart scripts: immutable + SRI-verified, so
  // serve instantly from cache and only touch the network on a miss. This is
  // the one cross-origin exception; everything else cross-origin still bypasses.
  if (CDN_ASSETS.includes(url.href)) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (response && (response.ok || response.type === 'opaque')) {
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, response.clone()));
          }
          return response;
        });
      })
    );
    return;
  }

  if (url.origin !== self.location.origin) return;

  // v3 P5: force a real network read for the data file. Without no-store the
  // HTTP cache could satisfy this fetch from a stale entry, so an installed PWA
  // kept serving old numbers even after a corrected build shipped — which would
  // have hidden the incident data-fix from exactly the returning users who saw
  // the bad numbers first.
  //
  // The document itself needs the same treatment. Pages serves index.html with
  // `Cache-Control: max-age=600`, and index.html is what carries every asset's
  // `?v=` cache-buster — so a returning visitor inside that window gets a
  // ten-minute-old document pointing at the PREVIOUS data URL, and the
  // busting does nothing. Fetching the navigation with no-store makes the
  // document the one thing guaranteed fresh, which is what every other
  // version pointer depends on.
  const isData = url.pathname.endsWith('/site_data.js');
  const isDocument = event.request.mode === 'navigate';
  event.respondWith(
    fetch(event.request, (isData || isDocument) ? { cache: 'no-store' } : undefined)
      .then(response => {
        if (response && response.ok && response.type !== 'opaque') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() =>
        caches.match(event.request).then(cached => {
          if (cached) return cached;
          if (event.request.mode === 'navigate') {
            return new Response(
              '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Offline</title>' +
              '<style>body{background:#0a0907;color:#f0c040;font-family:system-ui;display:flex;' +
              'justify-content:center;align-items:center;height:100vh;margin:0;text-align:center}' +
              '</style></head><body><div><h1>Offline</h1><p>CCA Entry Predictor is unavailable. ' +
              'Check your connection and try again.</p></div></body></html>',
              { status: 503, headers: { 'Content-Type': 'text/html' } }
            );
          }
          return new Response('', { status: 504 });
        })
      )
  );
});
