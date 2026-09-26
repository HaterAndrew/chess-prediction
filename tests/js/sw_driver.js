// Node driver for docs/sw.js, run by tests/test_service_worker.py.
//
// The service worker decides what the browser is allowed to serve from cache,
// which is the difference between a visitor seeing a corrected build and a
// visitor seeing yesterday's numbers. Each scenario runs the real file in a
// fresh sandbox with the ServiceWorkerGlobalScope pieces it touches and a
// Map-backed Cache, dispatches synthetic install and fetch events, awaits the
// promise handed to respondWith, and reports what was fetched, with which
// `init`, and what the cache holds afterwards.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SW = path.join(__dirname, '..', '..', 'docs', 'sw.js');
const ORIGIN = 'https://chessentries.com';
const SCOPE = `${ORIGIN}/`;
const CDN_CHART = 'https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js';

class Response {
  constructor(body, opts) {
    this.body = body;
    this.status = 200;
    this.type = 'basic';
    Object.assign(this, opts || {});
    this.ok = this.status >= 200 && this.status < 300;
  }
  clone() { return this; }
}

const flush = () => new Promise(resolve => setImmediate(resolve));

// One Map-backed cache keyed by absolute URL: enough to see what the worker
// keeps, and to seed what an earlier visit would have left behind.
function makeCache() {
  const store = new Map();
  const keyOf = r => (typeof r === 'string' ? new URL(r, SCOPE).href : r.url);
  const strip = u => u.split('?')[0];
  return {
    store,
    async match(r) { return store.get(keyOf(r)); },
    async put(r, resp) { store.set(keyOf(r), resp); },
    async delete(r) { return store.delete(keyOf(r)); },
    async keys(r, opts) {
      const all = [...store.keys()].map(url => ({ url }));
      if (!r) return all;
      const want = keyOf(r);
      if (opts && opts.ignoreSearch) return all.filter(k => strip(k.url) === strip(want));
      return all.filter(k => k.url === want);
    },
  };
}

function scenario({ offline = false, seed = [] } = {}) {
  const listeners = {};
  const fetchCalls = [];
  const cache = makeCache();
  for (const url of seed) cache.store.set(new URL(url, SCOPE).href, new Response('cached:' + url));
  const sandbox = {
    console, URL, Response,
    fetch(request, init) {
      const url = typeof request === 'string' ? request : request.url;
      fetchCalls.push({ url, init: init === undefined ? null : init });
      if (offline) return Promise.reject(new TypeError('Failed to fetch'));
      return Promise.resolve(new Response('net:' + url));
    },
    caches: {
      open: async () => cache,
      match: r => cache.match(r),
      keys: async () => ['cca-predictor-v1'],
      delete: async () => true,
    },
  };
  sandbox.self = {
    addEventListener(type, fn) { listeners[type] = fn; },
    location: { origin: ORIGIN },
    skipWaiting() {},
    clients: { claim() {} },
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SW, 'utf8'), sandbox, { filename: 'sw.js' });

  async function dispatch({ url, mode = 'no-cors', method = 'GET' }) {
    const before = fetchCalls.length;
    let promise = null;
    listeners.fetch({ request: { url, mode, method }, respondWith(p) { promise = p; } });
    const response = promise ? await promise : null;
    await flush();
    const calls = fetchCalls.slice(before);
    return {
      intercepted: promise !== null,
      fetched: calls.length > 0,
      init: calls.length ? calls[calls.length - 1].init : null,
      status: response ? response.status : null,
      body: response ? response.body : null,
    };
  }

  async function install() {
    const before = fetchCalls.length;
    let pending = null;
    listeners.install({ waitUntil(p) { pending = p; } });
    await pending;
    await flush();
    return fetchCalls.slice(before);
  }

  const cached = () => [...cache.store.keys()].map(u => u.replace(SCOPE, '')).sort();
  return { listeners, dispatch, install, cached };
}

const hashedApp = `${SCOPE}app.js?v=8dda437d9b`;
const hashedData = `${SCOPE}data/site_data.js?v=abc1234567`;
const font = `${SCOPE}fonts/archivo/archivo-latin.woff2`;
const warnings = `${SCOPE}audit_warnings.json`;

async function main() {
  const results = {};

  const base = scenario();
  results.registered_listeners = Object.keys(base.listeners).sort();
  results.install = { fetched: await base.install(), cached: base.cached() };

  const online = scenario();
  results.navigation = await online.dispatch({ url: SCOPE, mode: 'navigate' });
  results.hashed_miss = await online.dispatch({ url: hashedApp });
  results.hashed_miss.cached_after = online.cached();
  results.hashed_hit = await online.dispatch({ url: hashedApp });
  results.data_miss = await online.dispatch({ url: hashedData });
  results.data_hit = await online.dispatch({ url: hashedData });
  results.font_miss = await online.dispatch({ url: font });
  results.font_hit = await online.dispatch({ url: font });
  results.unhashed_first = await online.dispatch({ url: warnings });
  results.unhashed_second = await online.dispatch({ url: warnings });
  results.unhashed_second.cached_after = online.cached();
  results.cross_origin = await online.dispatch({ url: 'https://api.example/ask' });
  // The API routes live on the page's own origin and must bypass the cache.
  results.api_health = await online.dispatch({ url: `${SCOPE}health` });
  results.api_entrylist = await online.dispatch({ url: `${SCOPE}cca-entrylist?code=ABC` });
  results.post = await online.dispatch({ url: SCOPE, method: 'POST', mode: 'navigate' });
  results.cdn_miss = await online.dispatch({ url: CDN_CHART });
  results.cdn_hit = await online.dispatch({ url: CDN_CHART });

  const restamped = scenario({ seed: ['app.js?v=0000000000', 'data/site_data.js?v=1111111111'] });
  await restamped.dispatch({ url: hashedApp });
  await restamped.dispatch({ url: hashedData });
  results.restamp = { cached_after: restamped.cached() };

  const offline = scenario({ offline: true, seed: ['./', 'audit_warnings.json', 'app.js?v=8dda437d9b'] });
  results.offline_navigation = await offline.dispatch({ url: SCOPE, mode: 'navigate' });
  results.offline_unhashed = await offline.dispatch({ url: warnings });
  results.offline_hashed_hit = await offline.dispatch({ url: hashedApp });
  results.offline_hashed_miss = await offline.dispatch({ url: `${SCOPE}app.js?v=ffffffffff` });

  const bare = scenario({ offline: true });
  results.offline_navigation_nothing_cached = await bare.dispatch({ url: SCOPE, mode: 'navigate' });

  console.log(JSON.stringify(results, null, 2));
}

main().catch(err => { console.error(err); process.exit(1); });
