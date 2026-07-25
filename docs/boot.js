/**
 * boot.js — the two things that must happen before first paint.
 *
 * Extracted from inline <script> blocks in index.html so the page's CSP can
 * drop `script-src 'unsafe-inline'` (audit v3 S5). GitHub Pages is a static
 * host with no per-request nonce, so an external file loaded by a
 * render-blocking <script src> in <head> is the way to keep the pre-paint
 * timing while removing the inline allowance.
 *
 * Do NOT add `defer` or `async` to the tag that loads this file: the splash
 * classification has to be applied before the first paint or repeat visitors
 * get a flash of the splash screen.
 */
(function () {
  'use strict';

  // Splash is first-visit-only. Flag the root before paint so repeat visits and
  // deep-linked (#tab) loads skip it with no flash (CSS hides splash + reveals
  // main content for .splash-skip). See L6.
  try {
    var deep = location.hash && location.hash.length > 1;
    var seen = localStorage.getItem('cep:splash:seen') === '1';
    if (deep || seen) document.documentElement.classList.add('splash-skip');
  } catch (e) {}

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js');
  }
})();
