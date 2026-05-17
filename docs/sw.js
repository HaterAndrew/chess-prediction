// Network-first service worker. Always fetch fresh when online so deploys
// show immediately; fall back to cache only when offline.
// Cache name is bumped on each deploy that reshapes caching behavior so
// old caches from prior SW versions get purged on activate.

const CACHE_NAME = 'cca-predictor-v68';

const OFFLINE_FALLBACKS = [
  './',
  'index.html',
  'styles.css?v=27',
  'app.js?v=38',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js',
  'https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js'
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
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    fetch(event.request)
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
              '<style>body{background:#06090f;color:#f0c040;font-family:system-ui;display:flex;' +
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
