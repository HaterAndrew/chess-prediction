/**
 * boot.js — pre-paint bootstrap.
 *
 * Extracted from inline <script> blocks in index.html so the page's CSP can
 * drop `script-src 'unsafe-inline'` (audit v3 S5). GitHub Pages is a static
 * host with no per-request nonce, so an external file loaded by a
 * render-blocking <script src> in <head> keeps that CSP posture.
 *
 * The splash gate this file used to classify is gone (2026-07 makeover);
 * the only remaining job is service-worker registration.
 */
(function () {
  'use strict';

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js');
  }
})();
