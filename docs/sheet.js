// sheet.js — the sheet: a bottom sheet on phones; above them a centred
// dialog, or, given an anchor, a popover hung under the control that opened
// it (overlays.css draws all three from one markup shape). One sheet is open
// at a time; while it is, the page behind it is inert and focus stays inside,
// Escape and the scrim close it, and focus returns to the control that opened
// it. Markup: a `.sheet` root holding a `.sheet-scrim` and a `.sheet-panel`
// with role="dialog"; the group sheets in index.html are the reference.

let _sheetOpenId = null;
let _sheetLastFocus = null;
let _sheetAnchor = null;
const SHEET_FOCUSABLE = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), a[href], [tabindex="0"]';
const _sheetWide = window.matchMedia('(min-width: 640px)');

function _sheetFocusables(sheet) {
  return Array.from(sheet.querySelectorAll(SHEET_FOCUSABLE)).filter(el => el.offsetParent !== null);
}

// Hang the sheet under its anchor: its top is the anchor's bottom edge, and
// it aligns to the anchor's left edge unless that would run off the right
// of the viewport, in which case it aligns to the anchor's right edge. The
// sheet's data-width is the popover's width; phones ignore all of this and
// raise the sheet from the foot.
function _anchorSheet(sheet, anchor) {
  sheet.classList.remove('anchored');
  sheet.removeAttribute('data-align');
  if (!anchor || !_sheetWide.matches) return;
  const r = anchor.getBoundingClientRect();
  const width = Number(sheet.dataset.width) || 320;
  sheet.style.setProperty('--sheet-w', width + 'px');
  sheet.style.setProperty('--anchor-y', Math.round(r.bottom + 6) + 'px');
  sheet.style.setProperty('--anchor-x', Math.round(r.left) + 'px');
  sheet.style.setProperty('--anchor-right', Math.round(window.innerWidth - r.right) + 'px');
  sheet.dataset.align = r.left + width + 16 > window.innerWidth ? 'end' : 'start';
  sheet.classList.add('anchored');
}

function openSheet(id, anchor) {
  const sheet = document.getElementById(id);
  if (!sheet) return;
  if (_sheetOpenId && _sheetOpenId !== id) closeSheet();
  _sheetLastFocus = document.activeElement;
  _sheetAnchor = anchor || null;
  _anchorSheet(sheet, _sheetAnchor);
  if (_sheetAnchor) _sheetAnchor.setAttribute('aria-expanded', 'true');
  sheet.hidden = false;
  // The scroll lock goes on the root: overflow hidden on the body turns the
  // body into the sticky top bar's scroll box, and the bar scrolls away.
  document.documentElement.classList.add('sheet-open');
  const mc = document.getElementById('mainContent');
  if (mc) mc.inert = true;
  _sheetOpenId = id;
  _haptic(12);
  const panel = sheet.querySelector('.sheet-panel') || sheet;
  const first = _sheetFocusables(sheet)[0];
  // Focus on the next frame, once the sheet has laid out, so the browser
  // never scrolls a half-drawn panel into view.
  requestAnimationFrame(() => { (first || panel).focus({ preventScroll: true }); });
}

function closeSheet() {
  if (!_sheetOpenId) return;
  const sheet = document.getElementById(_sheetOpenId);
  if (sheet) sheet.hidden = true;
  document.documentElement.classList.remove('sheet-open');
  const mc = document.getElementById('mainContent');
  if (mc) mc.inert = false;
  _sheetOpenId = null;
  if (_sheetAnchor) _sheetAnchor.setAttribute('aria-expanded', 'false');
  _sheetAnchor = null;
  const back = _sheetLastFocus;
  _sheetLastFocus = null;
  try {
    if (back && typeof back.focus === 'function' && document.contains(back)) back.focus({ preventScroll: true });
  } catch (_) { /* the opener may have been re-rendered; nothing to restore */ }
}

function sheetIsOpen() { return _sheetOpenId !== null; }
function openSheetId() { return _sheetOpenId; }

// A popover's anchor moves when the layout changes under it; close rather
// than float free.
window.addEventListener('resize', () => { if (_sheetOpenId && _sheetAnchor) closeSheet(); });

// Escape closes; Tab and Shift+Tab wrap inside the open sheet.
document.addEventListener('keydown', e => {
  if (!_sheetOpenId) return;
  if (e.key === 'Escape') { e.preventDefault(); closeSheet(); return; }
  if (e.key !== 'Tab') return;
  const sheet = document.getElementById(_sheetOpenId);
  if (!sheet) return;
  const focusables = _sheetFocusables(sheet);
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const active = document.activeElement;
  if (e.shiftKey) {
    if (active === first || !sheet.contains(active)) { e.preventDefault(); last.focus(); }
  } else if (active === last) {
    e.preventDefault();
    first.focus();
  }
});
