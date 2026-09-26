// Node driver for docs/boot.js + docs/theme.js — run by tests/test_theme_js.py.
//
// The theme contract: light for everyone unless the visitor stored "dark",
// the OS preference never consulted, the toggle persisting its choice and
// keeping the meta theme-color and the button's ARIA state in step. Each
// scenario runs boot.js (and theme.js where the toggle is exercised) in a
// fresh vm context over a stub DOM and reports what the attribute ended as.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const DOCS = path.join(__dirname, '..', '..', 'docs');
const BOOT = fs.readFileSync(path.join(DOCS, 'boot.js'), 'utf8');
const THEME = fs.readFileSync(path.join(DOCS, 'theme.js'), 'utf8');

function makeStorage(initial, { throws = false } = {}) {
  const store = Object.assign({}, initial);
  return {
    getItem(k) { if (throws) throw new Error('storage disabled'); return k in store ? store[k] : null; },
    setItem(k, v) { if (throws) throw new Error('storage disabled'); store[k] = String(v); },
    _store: store,
  };
}

function makeDom({ osDark = false } = {}) {
  const attrs = {};
  const classes = new Set();
  const meta = { attrs: { name: 'theme-color', content: '#000000' },
                 setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; } };
  const button = { attrs: {}, title: '',
                   setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; } };
  const documentElement = {
    setAttribute(k, v) { attrs[k] = v; },
    getAttribute(k) { return k in attrs ? attrs[k] : null; },
    classList: { add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c) },
    appendChild() {},
  };
  const document = {
    documentElement,
    querySelector(sel) { return sel.includes('theme-color') ? meta : null; },
    querySelectorAll() { return []; },
    getElementById(id) { return id === 'themeToggle' ? button : null; },
    createElement() { return { style: {}, remove() {} }; },
  };
  const themes = { light: '#F7F4EC', dark: '#0a0907' };
  const sandbox = {
    document, meta, button,
    console,
    navigator: {},
    window: {
      addEventListener() {},
      matchMedia: q => ({ matches: q.includes('dark') ? osDark : false, addEventListener() {} }),
    },
    getComputedStyle(el) {
      return {
        getPropertyValue(name) {
          if (name === '--void') return themes[attrs['data-theme'] || 'light'];
          return '';
        },
        color: '',
      };
    },
    setTimeout(fn) { return 0; },
    clearTimeout() {},
    // theme.js collaborators that live in other files
    PALETTE: { tick: '#000', grid: '#000', fontDisplay: 'Inter' },
    rebuildPalette() {},
    _reduceMotion: () => false,
    _classes: classes,
  };
  sandbox.window.matchMedia = sandbox.window.matchMedia;
  return sandbox;
}

function runBoot({ stored, osDark = false, throws = false }) {
  const sb = makeDom({ osDark });
  sb.localStorage = makeStorage(stored, { throws });
  vm.createContext(sb);
  vm.runInContext(BOOT, sb, { filename: 'boot.js' });
  return sb.document.documentElement.getAttribute('data-theme');
}

function runToggle() {
  const sb = makeDom({});
  sb.localStorage = makeStorage({});
  vm.createContext(sb);
  vm.runInContext(BOOT, sb, { filename: 'boot.js' });
  vm.runInContext(THEME, sb, { filename: 'theme.js' });
  const before = {
    theme: sb.document.documentElement.getAttribute('data-theme'),
    pressed: sb.button.attrs['aria-pressed'],
    metaColor: sb.meta.attrs.content,
  };
  vm.runInContext('toggleTheme()', sb);
  const afterFirst = {
    theme: sb.document.documentElement.getAttribute('data-theme'),
    stored: sb.localStorage._store['cep:theme'],
    pressed: sb.button.attrs['aria-pressed'],
    label: sb.button.attrs['aria-label'],
    metaColor: sb.meta.attrs.content,
    switchingClassAdded: sb._classes.has('theme-switching'),
  };
  vm.runInContext('toggleTheme()', sb);
  const afterSecond = {
    theme: sb.document.documentElement.getAttribute('data-theme'),
    stored: sb.localStorage._store['cep:theme'],
  };
  return { before, afterFirst, afterSecond };
}

function runToggleReducedMotion() {
  const sb = makeDom({});
  sb.localStorage = makeStorage({});
  sb._reduceMotion = () => true;
  vm.createContext(sb);
  vm.runInContext(BOOT, sb, { filename: 'boot.js' });
  vm.runInContext(THEME, sb, { filename: 'theme.js' });
  vm.runInContext('toggleTheme()', sb);
  return { switchingClassAdded: sb._classes.has('theme-switching') };
}

const results = {
  no_store_os_light: runBoot({ stored: {} }),
  no_store_os_dark: runBoot({ stored: {}, osDark: true }),
  stored_dark: runBoot({ stored: { 'cep:theme': 'dark' } }),
  stored_light_os_dark: runBoot({ stored: { 'cep:theme': 'light' }, osDark: true }),
  stored_garbage: runBoot({ stored: { 'cep:theme': 'blue' } }),
  storage_throws: runBoot({ stored: {}, throws: true }),
  toggle: runToggle(),
  toggle_reduced_motion: runToggleReducedMotion(),
};

console.log(JSON.stringify(results, null, 2));
