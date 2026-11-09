// entry_value.js — the organizer's Value column on the Season table: the
// approximate dollar value of entries per event, from the Worker's
// /entry-value, which answers only to the shared key (worker/src/value-route.ts).
//
// The figures stay behind the key. The key field opens from the Value button
// on the Season table or the link chessentries.com/price (the Worker
// redirects it to /#value); after one
// unlock this browser keeps the key and
// the column loads on every visit. A failure always says so in the field's
// message line: the column never shows a blank or a $0 it does not know.

const VALUE_KEY_STORE = 'cep:value-key';
let _entryValues = null; // Map 'family|year' -> event, once unlocked
let _valueLoadSequence = 0;
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
  if (!ld || !Number.isFinite(ld.value) || ld.value === 0) return '';
  const span = ld.span > 1 ? ` / ${ld.span}d` : ' last day';
  return `<div class="td-value-sub">${ld.value > 0 ? '+' : '−'}${_fmtUsd(Math.abs(ld.value))}${span}</div>`;
}

function _receiptCell(ev) {
  const reasons = {
    no_receipts: 'No Chess Action receipts have been collected.',
    unmatched_count: 'Payment records do not match the entry forecast’s registration set.',
    stale_source: 'The payment or entry source needs a fresh update.',
    no_history: 'Not enough verified payment history to predict the final total.',
    no_fee: 'The current entry price is missing.',
    collection_failed: 'The latest payment collection failed.',
  };
  const explanation = 'Expected final Chess Action receipts after refunds, before processor fees. ' +
    'Separately collected onsite payments are excluded.';
  if (!Number.isFinite(ev.value)) {
    return `<td data-label="Value" class="num td-value-missing" title="${esc(reasons[ev.missing] || 'Receipts are unavailable.')}">unavailable</td>`;
  }
  const date = typeof ev.source_as_of === 'string' ? ev.source_as_of.slice(0, 10) : '';
  const detail = `${explanation} Source: ${date || 'unknown'}.${ev.stale ? ' Previous projection; refresh needed.' : ''}`;
  const note = ev.stale ? '<div class="td-value-sub">stale</div>' : _valueLastDay(ev.last_day);
  return `<td data-label="Value" class="num"><span class="td-value" tabindex="0" aria-label="${esc(detail)}" title="${esc(detail)}">${_fmtUsd(ev.value)}</span>${note}</td>`;
}

// The Value cell for one table row. Called by renderAllTournaments only
// while the column is unlocked.
function valueCell(t) {
  const ev = entryValueFor(t);
  if (!ev) return '<td data-label="Value" class="num">–</td>';
  if (ev.basis === 'chess_action_receipts') return _receiptCell(ev);
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
  const open = document.getElementById('valueOpen');
  if (open) open.hidden = entryValueOn();
}

const _VALUE_ERRORS = {
  401: 'Wrong key.',
  403: 'Value is not enabled on this host.',
  429: 'Too many wrong keys. Try again in an hour.',
  503: 'The private receipts source is not available.',
};

function _valueLoadFailed(message, forgetKey) {
  if (forgetKey) _writeValueKey('');
  _entryValues = null;
  _syncValueUi();
  renderAllTournaments();
  return _valueMessage(message);
}

async function loadEntryValues(key) {
  const sequence = ++_valueLoadSequence;
  let res;
  try {
    res = await fetch('/entry-value', { headers: { 'X-Value-Key': key }, cache: 'no-store' });
  } catch (e) {
    if (sequence !== _valueLoadSequence) return;
    return _valueLoadFailed('Could not reach the server.', false);
  }
  if (sequence !== _valueLoadSequence) return;
  if (!res.ok) return _valueLoadFailed(_VALUE_ERRORS[res.status] || `Value unavailable (HTTP ${res.status}).`, res.status === 401 || res.status === 403);
  let body;
  try {
    body = await res.json();
    if (!Array.isArray(body.events) || body.events.some(ev => !ev || typeof ev.family !== 'string' || !Number.isInteger(ev.year) ||
      (ev.value !== null && !Number.isFinite(ev.value)))) throw new Error('invalid response');
  } catch (e) {
    if (sequence !== _valueLoadSequence) return;
    return _valueLoadFailed('The server returned incomplete value data.', false);
  }
  if (sequence !== _valueLoadSequence) return;
  _entryValues = new Map(body.events.map(ev => [`${ev.family}|${ev.year}`, ev]));
  _writeValueKey(key);
  const input = document.getElementById('valueKey');
  if (input) input.value = '';
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
