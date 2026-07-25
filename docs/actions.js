// Event delegation for every interactive control on the page.
//
// v3 S5 (audit/AUDIT_2026-07-25.md). The markup used to carry ~155 runtime
// `onclick=`/`onkeydown=` attributes, which are inline script: they only run
// when the CSP allows `'unsafe-inline'` in script-src. Tightening the CSP
// without removing them shipped a completely dead UI to production once
// already — the page rendered perfectly, the console was silent, and nothing
// responded to a click. The handlers had to go before the CSP could be closed,
// and this file is where they went.
//
// How it works: markup declares intent with `data-act="name"` and reads its
// arguments from `data-*` attributes. Three delegated listeners on the document
// dispatch into the ACTIONS table below. Because dispatch is by name at click
// time, generated markup (app.js builds most of the tournament UI as HTML
// strings) needs no wiring of its own — it just sets the attribute.
//
// The action names are deliberately literal, matching what the old attribute
// called. That keeps this file reviewable against the diff that created it.

(function () {
  'use strict';

  // Read a numeric data attribute, tolerating an absent one.
  function num(el, name) {
    const raw = el.dataset[name];
    return raw === undefined ? undefined : Number(raw);
  }

  // Actions receive (element, event). Anything needing the raw event —
  // stopPropagation, the original `event` argument, a keyboard key — gets it.
  const ACTIONS = {
    // ---- chrome / navigation -------------------------------------------
    'dismiss-stale': function () {
      const banner = document.getElementById('staleBanner');
      if (banner) banner.style.display = 'none';
    },
    'dismiss-hint': function () {
      const hint = document.getElementById('firstRunHint');
      if (hint) hint.hidden = true;
      try { localStorage.setItem('cep:hint:seen', '1'); } catch (_) {}
    },
    'scroll-top': function () { window.scrollTo({ top: 0, behavior: 'smooth' }); },
    'open-cmdk': function () { openCmdK(); },
    'page-tab': function (el) { switchPageTab(el.dataset.tab); },
    'more-tab': function (el) { pickMoreTab(el.dataset.tab); },
    'toggle-more-menu': function (el, ev) { toggleMoreMenu(ev); },
    'open-tourney-picker': function (el, ev) { maybeOpenTourneyPicker(ev); },
    'add-to-compare': function (el, ev) {
      addToCompareSelected();
      ev.stopPropagation();
    },
    'close-cmdk': function () { closeCmdK(); },
    'cmdk-select': function (el) { _cmdkSelect(num(el, 'idx')); },
    'clear-data-entry': function () { clearDataEntry(); },

    // ---- tournament selection ------------------------------------------
    'select-tournament': function (el) { selectTournament(num(el, 'idx')); },
    'select-tournament-top': function (el) {
      selectTournament(num(el, 'idx'));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },
    'select-from-drop': function (el) { selectFromDrop(num(el, 'idx')); },
    'select-tourney-picker': function (el) { selectFromTourneyPicker(num(el, 'idx')); },
    'toggle-drop': function (el, ev) { toggleDrop(el.dataset.drop, ev); },
    'tourney-tab': function (el, ev) {
      ev.stopPropagation();
      setTourneyTab(el.dataset.tab);
    },

    // ---- tables ---------------------------------------------------------
    'sort-table': function (el, ev) { sortTable(el.dataset.col, ev); },
    'filter-tourney-table': function (el) { filterTourneyTable(el.dataset.filter); },

    // ---- performance ----------------------------------------------------
    'perf-year': function (el) { perfSelectYear(el.dataset.year); },

    // ---- puzzles --------------------------------------------------------
    'puzzle-nav': function (el) { puzzleNav(num(el, 'delta')); },
    'puzzle-hint': function () { puzzleGiveHint(); },
    'puzzle-retry': function () { puzzleRetry(); },
    'puzzle-square': function (el) { puzzleSquareClick(num(el, 'r'), num(el, 'c')); },
    'load-puzzle': function (el) { loadPuzzle(num(el, 'idx')); },

    // ---- email ----------------------------------------------------------
    'email-select-all': function () { emailSelectAll(); },
    'email-select-none': function () { emailSelectNone(); },
    'email-select-live': function () { emailSelectLiveOnly(); },
    'email-select-close': function () { emailSelectClose(); },
    'email-length': function (el) { setEmailLength(el.dataset.len); },
    'email-format': function (el) { setEmailFormat(el.dataset.fmt); },
    'email-generate': function () { generateEmail(); },
    'email-copy': function () { copyEmail(); },
    'email-copy-html': function () { copyEmailHTML(); },
    'email-split-tab': function (el) { setEmailSplitTab(el.dataset.tab); },

    // ---- compare --------------------------------------------------------
    'compare-slot-remove': function (el) { compareSlotRemove(num(el, 'slot')); },
  };

  // Actions bound to input/change rather than click. Kept separate so a stray
  // click on a text field cannot fire one.
  const INPUT_ACTIONS = {
    'filter-tourney-table-input': function () { filterTourneyTable(); },
    'filter-tourney-hist': function (el) { filterTourneyHistResults(el.value); },
    'filter-hist': function (el) { filterHistResults(el.value); },
    'compare-slot-changed': function (el) { compareSlotChanged(num(el, 'slot'), el.value); },
  };

  // Keydown actions that are NOT plain activation — they interpret the key
  // themselves (arrow navigation on the puzzle board).
  const KEY_ACTIONS = {
    'puzzle-board': function (el, ev) {
      puzzleBoardKeydown(ev, num(el, 'r'), num(el, 'c'), num(el, 'ri'), num(el, 'ci'));
    },
  };

  // `ev.target` is not always an Element. A keydown with nothing focused can
  // target `document`, and a click can land on a text node; neither has
  // .closest, and calling it threw a TypeError that killed the whole listener
  // for that event. Resolve to the nearest Element first, or give up quietly.
  function closestFrom(ev, selector) {
    const t = ev.target;
    if (!t) return null;
    const el = t.nodeType === 1 ? t : t.parentElement;
    return el && el.closest ? el.closest(selector) : null;
  }

  function runInput(el, ev) {
    const fn = INPUT_ACTIONS[el.dataset.inputact];
    if (typeof fn === 'function') fn(el, ev);
  }

  document.addEventListener('click', function (ev) {
    const el = closestFrom(ev, '[data-act]');
    if (!el) return;
    const fn = ACTIONS[el.dataset.act];
    if (typeof fn === 'function') fn(el, ev);
  });

  // Keyboard activation. An element that responds to a click must also respond
  // to Enter (and Space, where the original markup accepted it) or it is
  // unreachable without a mouse. `data-keys="enter"` reproduces the handlers
  // that deliberately took Enter alone.
  document.addEventListener('keydown', function (ev) {
    const custom = closestFrom(ev, '[data-keyact]');
    if (custom) {
      const fn = KEY_ACTIONS[custom.dataset.keyact];
      if (typeof fn === 'function') {
        fn(custom, ev);
        return;
      }
    }

    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    const el = closestFrom(ev, '[data-act]');
    if (!el || !el.dataset.keyable) return;
    if (ev.key === ' ' && el.dataset.keys === 'enter') return;

    // Native buttons and links already activate on Enter/Space; intercepting
    // would fire the action twice.
    const tag = el.tagName;
    if (tag === 'BUTTON' || tag === 'A' || tag === 'INPUT' || tag === 'TEXTAREA') return;

    const fn = ACTIONS[el.dataset.act];
    if (typeof fn !== 'function') return;
    if (el.dataset.keys !== 'enter') ev.preventDefault();
    fn(el, ev);
  });

  document.addEventListener('input', function (ev) {
    const el = closestFrom(ev, '[data-inputact]');
    if (el) runInput(el, ev);
  });

  document.addEventListener('change', function (ev) {
    const el = closestFrom(ev, '[data-inputact]');
    if (el) runInput(el, ev);
  });

  // The skip link reveals itself on focus. Focus does not bubble, so these use
  // the capturing focusin/focusout pair rather than focus/blur.
  document.addEventListener('focusin', function (ev) {
    const el = closestFrom(ev, '[data-reveal-on-focus]');
    if (el) el.style.top = '0';
  });
  document.addEventListener('focusout', function (ev) {
    const el = closestFrom(ev, '[data-reveal-on-focus]');
    if (el) el.style.top = el.dataset.revealOnFocus;
  });

  // Exposed for tests: the set of names the markup is allowed to reference.
  window.__ACTION_NAMES = {
    click: Object.keys(ACTIONS),
    input: Object.keys(INPUT_ACTIONS),
    key: Object.keys(KEY_ACTIONS),
  };
})();
