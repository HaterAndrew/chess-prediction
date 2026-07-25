// Node driver for docs/sw.js — exercised by tests/test_service_worker.js's
// pytest wrapper, tests/test_service_worker.py.
//
// The service worker decides what the browser is allowed to serve from cache,
// which is the difference between a visitor seeing a corrected build and a
// visitor seeing yesterday's numbers. That logic had never been executed by a
// test. This runs the real file in a sandbox with the ServiceWorkerGlobalScope
// pieces it touches, dispatches synthetic fetch events, and reports the
// `init` each one passed to fetch.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SW = path.join(__dirname, '..', '..', 'docs', 'sw.js');
const ORIGIN = 'https://haterandrew.github.io';

const listeners = {};
const fetchCalls = [];

function stubResponse() {
  return { ok: true, type: 'basic', clone() { return this; } };
}

const sandbox = {
  console,
  URL,
  Response: class {
    constructor(body, opts) {
      this.body = body;
      Object.assign(this, opts || {});
    }
  },
  fetch(request, init) {
    const url = typeof request === 'string' ? request : request.url;
    fetchCalls.push({ url, init: init === undefined ? null : init });
    return Promise.resolve(stubResponse());
  },
  caches: {
    open: async () => ({ put: async () => {}, addAll: async () => {} }),
    match: async () => undefined,
    keys: async () => [],
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

// Dispatch one fetch event and report what the handler did with it.
function dispatch({ url, mode = 'no-cors', method = 'GET' }) {
  const before = fetchCalls.length;
  let intercepted = false;
  const request = { url, mode, method };
  listeners.fetch({
    request,
    respondWith() { intercepted = true; },
  });
  const call = fetchCalls.length > before ? fetchCalls[fetchCalls.length - 1] : null;
  return { intercepted, init: call ? call.init : null };
}

const results = {
  registered_listeners: Object.keys(listeners).sort(),
  // The document carries every asset's ?v= pointer, so it has to be the one
  // thing that is never served from a stale HTTP cache entry.
  navigation: dispatch({ url: `${ORIGIN}/chess-prediction/`, mode: 'navigate' }),
  // The data file changes nightly under a stable path.
  site_data: dispatch({ url: `${ORIGIN}/chess-prediction/data/site_data.js?v=abc1234567` }),
  // Content-hashed assets are safe to let the HTTP cache serve.
  hashed_script: dispatch({ url: `${ORIGIN}/chess-prediction/app.js?v=8dda437d9b` }),
  // Cross-origin (the Ask Worker) must bypass the SW entirely.
  cross_origin: dispatch({ url: 'https://chess-ask.workers.dev/ask' }),
  // Non-GET is never intercepted.
  post: dispatch({ url: `${ORIGIN}/chess-prediction/`, method: 'POST', mode: 'navigate' }),
};

console.log(JSON.stringify(results, null, 2));
