// disclosure.js — the open state of the details.sect sections on the Forecast.

// ══════════════════════════════════════════════════════════
// SECTION DISCLOSURE
// ══════════════════════════════════════════════════════════
// Each details.sect on the Forecast carries data-open:
// "always" (open on every width), "wide" (open from 640 px up, closed on a
// phone) or "closed" (closed until the visitor opens it; never touched here).
// The width rule applies when the width class changes, so a section the
// visitor toggled keeps their choice until it does. app.js opens every
// section for print and restores them after.
let _sectWide = null;
function syncSectionDisclosure(force) {
  const wide = window.innerWidth >= 640;
  if (!force && wide === _sectWide) return;
  _sectWide = wide;
  document.querySelectorAll('details.sect').forEach(d => {
    const mode = d.dataset.open || 'always';
    if (mode === 'always') d.open = true;
    else if (mode === 'wide') d.open = wide;
  });
}
