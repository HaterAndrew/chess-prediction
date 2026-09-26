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
 *   2. register the service worker.
 */
(function () {
  'use strict';

  var theme = 'light';
  try {
    if (localStorage.getItem('cep:theme') === 'dark') theme = 'dark';
  } catch (_) {}
  document.documentElement.setAttribute('data-theme', theme);

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js');
  }
})();
