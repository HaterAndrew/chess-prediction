// gestures.js — the two phone gestures, on the house motion (motion.js):
// a bottom sheet you drag shut, and a swipe between views that follows the
// finger. Both track 1:1 while the finger is down, resist past the edges,
// and on release project the momentum to pick the resting point, then hand
// the finger's velocity to a spring. An animation in flight can be grabbed.
// Fingers use touch events (so the drag can stop the page scrolling only
// once it has decided to be a drag); a mouse on a phone-width window uses
// pointer events. Neither runs above 639 px.

const GESTURE_LOCK = 10;          // px before a drag commits to a direction
const SWIPE_EDGE_GUARD = 28;      // px kept clear for the browser's own back swipe
const SWIPE_IGNORE = 'canvas, .tourney-table-wrap, .compare-chart-wrap, .sheet, .email-output, .email-preview, iframe, .chess-board, .cal-track-wrap, .up-next-strip, #perfTable, .comp-table-wrap, .compare-table-wrap, input, textarea, select';

// One drag session from either input, with a velocity tracker per axis.
// handlers: start(p) → false to decline; move(p, ev); end(p).
// p carries x, y, dx, dy, vx, vy, time, target.
function _trackDrag(root, handlers) {
  let active = null;
  const vx = new VelocityTracker();
  const vy = new VelocityTracker();

  function begin(x, y, target, time) {
    const p = { x, y, dx: 0, dy: 0, vx: 0, vy: 0, time, target, startX: x, startY: y };
    if (handlers.start(p) === false) return;
    vx.reset(); vy.reset();
    vx.push(x, time); vy.push(y, time);
    active = p;
  }
  function move(x, y, time, ev) {
    if (!active) return;
    vx.push(x, time); vy.push(y, time);
    active.x = x; active.y = y; active.time = time;
    active.dx = x - active.startX; active.dy = y - active.startY;
    handlers.move(active, ev);
  }
  function end(time) {
    if (!active) return;
    active.vx = vx.velocity(); active.vy = vy.velocity(); active.time = time;
    const p = active;
    active = null;
    handlers.end(p);
  }

  root.addEventListener('touchstart', e => {
    if (e.touches.length !== 1) { if (active) end(e.timeStamp); return; }
    const t = e.touches[0];
    begin(t.clientX, t.clientY, e.target, e.timeStamp);
  }, { passive: true });
  root.addEventListener('touchmove', e => {
    if (!active || e.touches.length !== 1) return;
    const t = e.touches[0];
    move(t.clientX, t.clientY, e.timeStamp, e);
  }, { passive: false });
  root.addEventListener('touchend', e => end(e.timeStamp), { passive: true });
  root.addEventListener('touchcancel', e => end(e.timeStamp), { passive: true });

  root.addEventListener('pointerdown', e => {
    if (e.pointerType !== 'mouse' || e.button !== 0) return;
    begin(e.clientX, e.clientY, e.target, e.timeStamp);
  });
  window.addEventListener('pointermove', e => {
    if (e.pointerType !== 'mouse') return;
    move(e.clientX, e.clientY, e.timeStamp, e);
  });
  window.addEventListener('pointerup', e => { if (e.pointerType === 'mouse') end(e.timeStamp); });
}

// ── The sheet: drag it down to close ──
// The drag starts anywhere on the panel once the finger moves down with
// nothing under it scrolled; a panel that is scrolled keeps scrolling. The
// scrim thins as the sheet goes. Released past a third of its height, or
// flicked, it leaves with the finger's speed; otherwise it springs back.
function _sheetDrag() {
  let panel = null;
  let scrim = null;
  let height = 0;
  let locked = null;   // 'drag' | 'scroll' | null
  let anim = null;

  function scrolledInside(target) {
    let el = target;
    while (el && el !== panel) {
      if (el.scrollTop > 0) return true;
      el = el.parentElement;
    }
    return panel && panel.scrollTop > 0;
  }
  function place(y) {
    panel.style.transform = y ? `translateY(${y}px)` : '';
    if (scrim) scrim.style.opacity = y ? String(Math.max(0, 1 - y / height * 0.9)) : '';
  }
  function finish() {
    if (panel) { panel.style.transform = ''; panel.style.transition = ''; }
    if (scrim) scrim.style.opacity = '';
    panel = null; scrim = null; anim = null;
  }

  _trackDrag(document, {
    start(p) {
      if (!_mobileVP() || !sheetIsOpen()) return false;
      const sheet = document.getElementById(openSheetId());
      const target = p.target && p.target.closest ? p.target.closest('.sheet-panel') : null;
      if (!sheet || !target || !sheet.contains(target)) return false;
      if (anim) { anim.cancel(); anim = null; }
      panel = target;
      scrim = sheet.querySelector('.sheet-scrim');
      height = panel.getBoundingClientRect().height || 1;
      locked = null;
      return true;
    },
    move(p, ev) {
      if (!panel) return;
      if (!locked) {
        if (Math.abs(p.dx) < GESTURE_LOCK && Math.abs(p.dy) < GESTURE_LOCK) return;
        locked = (p.dy > Math.abs(p.dx) && !scrolledInside(p.target)) ? 'drag' : 'scroll';
        if (locked === 'drag') panel.classList.add('dragging');
      }
      if (locked !== 'drag') return;
      if (ev && ev.cancelable) ev.preventDefault();
      place(p.dy >= 0 ? p.dy : rubberBand(p.dy, height, 0.3));
    },
    end(p) {
      if (!panel) return;
      const wasDrag = locked === 'drag';
      locked = null;
      if (!wasDrag) { finish(); return; }
      panel.classList.remove('dragging');
      const y = Math.max(0, p.dy);
      const projected = y + projectMomentum(p.vy);
      const closing = projected > height / 3 || p.vy > 900;
      const panelRef = panel;
      anim = animateSpring({
        from: y, to: closing ? height + 8 : 0, velocity: closing ? p.vy : p.vy / 2,
        response: closing ? MOTION.throw.response : MOTION.settle.response,
        damping: closing ? 1 : MOTION.settle.damping,
        onUpdate: v => { if (panel === panelRef) place(Math.max(v, closing ? 0 : -height)); },
        onDone: () => { finish(); if (closing) closeSheet({ instant: true }); },
      });
    },
  });
}

// ── The views: swipe between them ──
// The open view follows the finger sideways and resists at the first and
// the last view. Released past a third of the width, or flicked, it slides
// off and the next view slides in from the far side; otherwise it settles
// back. The order is the nav's (PAGE_TAB_ORDER).
function _viewSwipe() {
  let panel = null;
  let width = 0;
  let locked = null;
  let anim = null;
  let busy = false;   // only while the outgoing view is leaving
  let offset = 0;     // the open view's current x, so a grab continues from it
  let base = 0;

  function settle(el, from, velocity) {
    anim = animateSpring({
      from, to: 0, velocity, response: MOTION.settle.response, damping: MOTION.settle.damping, epsilon: 0.3,
      onUpdate: v => place(el, v),
      onDone: () => { place(el, 0); anim = null; },
    });
  }
  function neighbour(dir) {
    const idx = PAGE_TAB_ORDER.indexOf(_currentTab);
    const next = idx + dir;
    return next >= 0 && next < PAGE_TAB_ORDER.length ? PAGE_TAB_ORDER[next] : null;
  }
  function place(el, x) {
    offset = x;
    el.style.transform = x ? `translateX(${x}px)` : '';
  }
  // The next view arrives from the far side with the finger's speed; the
  // arrival can be grabbed and swiped again.
  function slideIn(tab, fromX, velocity) {
    switchPageTab(tab);
    window.scrollTo({ top: 0, behavior: 'auto' });
    const incoming = document.getElementById('panel-' + tab);
    place(incoming, fromX);
    busy = false;
    anim = animateSpring({
      from: fromX, to: 0, velocity, response: MOTION.move.response, damping: MOTION.move.damping, epsilon: 0.3,
      onUpdate: v => place(incoming, v),
      onDone: () => { place(incoming, 0); anim = null; },
    });
  }

  _trackDrag(document, {
    start(p) {
      if (!_mobileVP() || busy || sheetIsOpen()) return false;
      if (p.x < SWIPE_EDGE_GUARD || p.x > window.innerWidth - SWIPE_EDGE_GUARD) return false;
      if (p.target && p.target.closest && p.target.closest(SWIPE_IGNORE)) return false;
      const active = document.querySelector('.page-tab-panel.active');
      if (!active || !active.contains(p.target)) return false;
      // A view still arriving is grabbed where it is.
      if (anim) { anim.cancel(); anim = null; base = offset; } else { base = 0; offset = 0; }
      panel = active;
      width = window.innerWidth;
      locked = null;
      return true;
    },
    move(p, ev) {
      if (!panel) return;
      if (!locked) {
        if (Math.abs(p.dx) < GESTURE_LOCK && Math.abs(p.dy) < GESTURE_LOCK) return;
        locked = Math.abs(p.dx) > Math.abs(p.dy) * 1.2 ? 'swipe' : 'scroll';
        if (locked === 'swipe') panel.classList.add('dragging');
      }
      if (locked !== 'swipe') return;
      if (ev && ev.cancelable) ev.preventDefault();
      const x = base + p.dx;
      place(panel, neighbour(x < 0 ? 1 : -1) ? x : rubberBand(x, width, 0.35));
    },
    end(p) {
      if (!panel) return;
      const wasSwipe = locked === 'swipe';
      locked = null;
      const outgoing = panel;
      panel = null;
      if (!wasSwipe) { if (base) settle(outgoing, base, 0); return; }
      outgoing.classList.remove('dragging');
      const x = offset;
      const dir = x < 0 ? 1 : -1;
      const target = neighbour(dir);
      const projected = x + projectMomentum(p.vx);
      const go = !!target && (Math.abs(projected) > width / 3 || Math.abs(p.vx) > 700) && Math.sign(projected) === Math.sign(x);
      if (!go) { settle(outgoing, x, p.vx / 2); return; }
      busy = true;
      anim = animateSpring({
        from: x, to: -dir * width, velocity: p.vx, response: MOTION.throw.response, damping: 1, epsilon: 0.5,
        onUpdate: v => place(outgoing, v),
        onDone: () => { place(outgoing, 0); slideIn(target, dir * width, p.vx); },
      });
    },
  });
}

_sheetDrag();
_viewSwipe();
