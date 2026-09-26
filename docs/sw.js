// Network-first service worker. Always fetch fresh when online so deploys
// show immediately; fall back to cache only when offline.
// Cache name is bumped on each deploy that reshapes caching behavior so
// old caches from prior SW versions get purged on activate.

const CACHE_NAME = 'cca-predictor-v79';

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
  'boot.js?v=495fc9422f',
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
  'data/site_data.js?v=8d6b725c62',
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
              '<style>body{background:#F7F4EC;color:#28241B;font-family:Inter,system-ui,sans-serif;display:flex;' +
              'justify-content:center;align-items:center;height:100vh;margin:0;text-align:center}' +
              'h1{color:#9A7010}</style></head><body><div><h1>Offline</h1><p>CCA Entry Predictor is unavailable. ' +
              'Check your connection and try again.</p></div></body></html>',
              { status: 503, headers: { 'Content-Type': 'text/html' } }
            );
          }
          return new Response('', { status: 504 });
        })
      )
  );
});
