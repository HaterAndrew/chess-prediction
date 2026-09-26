/**
 * boot.js — pre-paint bootstrap.
 *
 * Extracted from inline <script> blocks in index.html so the page's CSP can
 * drop `script-src 'unsafe-inline'` (audit v3 S5). GitHub Pages is a static
 * host with no per-request nonce, so an external file loaded by a
 * render-blocking <script src> in <head> keeps that CSP posture.
 *
 * The splash gate this file used to classify is gone (2026-07 makeover).
 * Two jobs remain, both of which must run before first paint:
 *   1. set the theme attribute from the stored preference so the page never
 *      flashes the wrong theme (light is the default for everyone; dark is
 *      opt-in through the header toggle, see theme.js);
 *   2. register the service worker, once the page has loaded: registering
 *      before that starts the worker's install precache while the page is
 *      still fetching its own scripts, and the two compete for bandwidth
 *      on exactly the cold visit that matters.
 */
(function () {
  'use strict';

  var theme = 'light';
  try {
    if (localStorage.getItem('cep:theme') === 'dark') theme = 'dark';
  } catch (_) {}
  document.documentElement.setAttribute('data-theme', theme);

  // The first-run note is in the page for a new visitor; a returning one
  // (who saw the old splash gate, or dismissed the note) is marked here so
  // the note is never laid out and then removed.
  try {
    if (localStorage.getItem('cep:splash:seen') || localStorage.getItem('cep:hint:seen')) {
      document.documentElement.setAttribute('data-hint', 'seen');
    }
  } catch (_) {}

  // The site lives at https://chessentries.com. A visit to the old GitHub
  // Pages address goes there with its path, query and hash intact, and the
  // old service worker is unregistered first so it cannot resurrect this
  // copy. The flag stays so a rollback is a one-line change.
  var CUTOVER = true;
  if (CUTOVER && typeof location !== 'undefined' && /\.github\.io$/.test(location.hostname)) {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.getRegistrations().then(function (regs) {
        regs.forEach(function (r) { r.unregister(); });
      });
    }
    var path = location.pathname.replace(/^\/chess-prediction\/?/, '/');
    location.replace('https://chessentries.com' + path + location.search + location.hash);
    return;
  }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('sw.js');
    });
  }
})();
