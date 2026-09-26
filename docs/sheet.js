// sheet.js — the sheet: a bottom sheet on phones, a centred dialog above
// them (overlays.css draws both from one markup shape). One sheet is open at
// a time; while it is, the page behind it is inert and focus stays inside,
// Escape and the scrim close it, and focus returns to the control that opened
// it. Markup: a `.sheet` root holding a `.sheet-scrim` and a `.sheet-panel`
// with role="dialog"; the More sheet in index.html is the reference.

let _sheetOpenId = null;
let _sheetLastFocus = null;
const SHEET_FOCUSABLE = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), a[href], [tabindex="0"]';

function _sheetFocusables(sheet) {
  return Array.from(sheet.querySelectorAll(SHEET_FOCUSABLE)).filter(el => el.offsetParent !== null);
}

function openSheet(id) {
  const sheet = document.getElementById(id);
  if (!sheet) return;
  if (_sheetOpenId && _sheetOpenId !== id) closeSheet();
  _sheetLastFocus = document.activeElement;
  sheet.hidden = false;
  document.body.classList.add('sheet-open');
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
  document.body.classList.remove('sheet-open');
  const mc = document.getElementById('mainContent');
  if (mc) mc.inert = false;
  _sheetOpenId = null;
  const back = _sheetLastFocus;
  _sheetLastFocus = null;
  try {
    if (back && typeof back.focus === 'function' && document.contains(back)) back.focus({ preventScroll: true });
  } catch (_) { /* the opener may have been re-rendered; nothing to restore */ }
}

function sheetIsOpen() { return _sheetOpenId !== null; }

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
