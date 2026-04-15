const CACHE_NAME = 'cca-predictor-v1';

const STATIC_ASSETS = [
  'styles.css?v=1',
  'app.js',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js',
  'https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js'
];

const DYNAMIC_PAGES = [
  'index.html',
  'website_data.json'
];

// Install: pre-cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      cache.addAll([...STATIC_ASSETS, ...DYNAMIC_PAGES])
    )
  );
  self.skipWaiting();
});

// Activate: purge old cache versions
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch: network-first for dynamic content, cache-first for static assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Determine if this is a dynamic resource (should be fresh)
  const isDynamic = url.pathname.endsWith('/') ||
    url.pathname.endsWith('index.html') ||
    url.pathname.endsWith('website_data.json');

  if (isDynamic) {
    // Network-first: try network, fall back to cache, then offline message
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() =>
          caches.match(event.request).then(cached =>
            cached || new Response(
              '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Offline</title>' +
              '<style>body{background:#06090f;color:#f0c040;font-family:system-ui;display:flex;' +
              'justify-content:center;align-items:center;height:100vh;margin:0;text-align:center}' +
              '</style></head><body><div><h1>Offline</h1><p>CCA Entry Predictor is unavailable. ' +
              'Check your connection and try again.</p></div></body></html>',
              { status: 503, headers: { 'Content-Type': 'text/html' } }
            )
          )
        )
    );
  } else {
    // Cache-first: try cache, fall back to network
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        });
      })
    );
  }
});
