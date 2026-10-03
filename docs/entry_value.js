// entry_value.js — the organizer's Value column on the Season table: the
// approximate dollar value of entries per event, from the Worker's
// /entry-value, which answers only to the shared key (worker/src/value-route.ts).
//
// Nothing shows for the public. The key field opens from the private link
// chessentries.com/price (the Worker redirects it to /#value); after one
// unlock this browser keeps the key and
// the column loads on every visit. A failure always says so in the field's
// message line: the column never shows a blank or a $0 it does not know.

const VALUE_KEY_STORE = 'cep:value-key';
let _entryValues = null; // Map 'family|year' -> event, once unlocked
// Read now: app.js's init() rewrites the hash to the opening view
// (updateHash) before DOMContentLoaded, when _startEntryValue runs.
const _openedFromValueLink = location.hash === '#value';

function _readValueKey() {
  try { return localStorage.getItem(VALUE_KEY_STORE) || ''; } catch (e) { return ''; }
}

function _writeValueKey(key) {
  try {
    if (key) localStorage.setItem(VALUE_KEY_STORE, key);
    else localStorage.removeItem(VALUE_KEY_STORE);
  } catch (e) { /* private window: the key lasts this visit only */ }
}

function entryValueOn() { return _entryValues !== null; }

function entryValueFor(t) {
  return _entryValues ? _entryValues.get(`${t.family}|${t.year}`) || null : null;
}

function _fmtUsd(n) { return '$' + fmt(n); }

function _valueLastDay(ld) {
  if (!ld || ld.entries <= 0) return '';
  const span = ld.span > 1 ? ` / ${ld.span}d` : ' last day';
  return `<div class="td-value-sub">+${_fmtUsd(ld.value)}${span}</div>`;
}

// The Value cell for one table row. Called by renderAllTournaments only
// while the column is unlocked.
function valueCell(t) {
  const ev = entryValueFor(t);
  if (!ev) return '<td data-label="Value" class="num">–</td>';
  if (ev.missing) return '<td data-label="Value" class="num td-value-missing">no fee posted</td>';
  const basis = ev.basis === 'onsite' ? ' title="Only the at-the-door fee is posted"' : '';
  return `<td data-label="Value" class="num"><span class="td-value"${basis}>${_fmtUsd(ev.value)}</span>${_valueLastDay(ev.last_day)}</td>`;
}

function _valueMessage(text) {
  const form = document.getElementById('valueUnlock');
  const msg = document.getElementById('valueMsg');
  if (msg) msg.textContent = text;
  if (form && text) form.hidden = false;
}

function _syncValueUi() {
  const th = document.getElementById('thValue');
  if (th) th.hidden = !entryValueOn();
  const form = document.getElementById('valueUnlock');
  if (form && entryValueOn()) form.hidden = true;
}

const _VALUE_ERRORS = {
  401: 'Wrong key.',
  403: 'Value is not enabled on this host.',
  429: 'Too many wrong keys. Try again in an hour.',
};

async function loadEntryValues(key) {
  let res;
  try {
    res = await fetch('/entry-value', { headers: { 'X-Value-Key': key }, cache: 'no-store' });
  } catch (e) {
    return _valueMessage('Could not reach the server: ' + e.message);
  }
  if (res.status === 401) _writeValueKey('');
  if (!res.ok) return _valueMessage(_VALUE_ERRORS[res.status] || `Value unavailable (HTTP ${res.status}).`);
  const body = await res.json();
  _entryValues = new Map(body.events.map(ev => [`${ev.family}|${ev.year}`, ev]));
  _writeValueKey(key);
  _valueMessage('');
  _syncValueUi();
  renderAllTournaments();
}

function _openValueUnlock() {
  switchPageTab('season');
  const form = document.getElementById('valueUnlock');
  if (!form) return;
  form.hidden = false;
  const input = document.getElementById('valueKey');
  if (input) input.focus();
}

function _startEntryValue() {
  if (_openedFromValueLink) _openValueUnlock();
  const key = _readValueKey();
  if (key) loadEntryValues(key);
}

document.addEventListener('submit', function (ev) {
  if (!ev.target || ev.target.id !== 'valueUnlock') return;
  ev.preventDefault();
  const input = document.getElementById('valueKey');
  const key = input ? input.value.trim() : '';
  if (!key) return _valueMessage('Enter the key.');
  _valueMessage('Checking…');
  loadEntryValues(key);
});

window.addEventListener('hashchange', function () {
  if (location.hash === '#value') _openValueUnlock();
});

// site.js is a deferred script, so it runs before DOMContentLoaded and this
// fires after the whole bundle, app.js's init() included. Running at
// evaluation time instead would reach switchPageTab before app.js has set
// up the tab state it reads.
document.addEventListener('DOMContentLoaded', _startEntryValue);
