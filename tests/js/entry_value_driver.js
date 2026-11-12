// Synthetic receipts deliberately differ from the expected final amount.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const root = path.join(__dirname, '../..');
const nodes = new Map();
const node = id => {
  if (!nodes.has(id)) nodes.set(id, { hidden: true, value: '', textContent: '', innerHTML: '' });
  return nodes.get(id);
};
// Read the shipped attributes so missing keyboard wiring cannot pass a mock.
const markup = fs.readFileSync(path.join(root, 'docs/index.html'), 'utf8');
const headers = ['thValue', 'thActual'].map(id => {
  const tag = markup.match(new RegExp('<th\\b[^>]*id="' + id + '"[^>]*>'));
  const attrs = Object.fromEntries([...(tag ? tag[0] : '').matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1], m[2]]));
  return Object.assign(node(id), { nodeType: 1, tagName: 'TH',
    dataset: { act: attrs['data-act'], col: attrs['data-col'], keyable: attrs['data-keyable'] },
    classList: { add() {}, remove() {} }, closest() { return this; },
    getAttribute: name => attrs[name] ?? null,
    setAttribute: (name, value) => { attrs[name] = value; },
    removeAttribute: name => { delete attrs[name]; },
  });
});
const listeners = new Map();
let reply;
const context = vm.createContext({
  document: { getElementById: node,
    querySelector: selector => headers.find(h => selector.includes('data-col="' + h.dataset.col + '"')) || null,
    querySelectorAll: selector => selector === '.tourney-table th.sortable' ? headers : [],
    addEventListener(type, fn) { listeners.set(type, [...(listeners.get(type) || []), fn]); } },
  window: { addEventListener() {} }, location: { hash: '' },
  localStorage: { getItem: () => '', setItem() {}, removeItem() {} },
  fetch: async (url, options) => {
    assert.equal(url, '/entry-value');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.headers['X-Value-Key'], 'synthetic-key');
    return reply;
  },
  _syncLikelyRangeTitle() {},
  esc: text => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;'),
  TOURNAMENT_DATA: { tournaments: [] },
});
for (const name of ['util_core.js', 'panels_grid.js', 'entry_value.js', 'actions.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'docs', name), 'utf8'), context, { filename: name });
}
const run = code => vm.runInContext(code, context);
const event = (family, actual, value = 1000, extra = {}) => ({
  family, year: 2027, basis: 'chess_action_receipts', value, actual_cents: actual,
  source_as_of: '2026-11-12T03:20:00Z', stale: false, missing: null, ...extra,
});
const card = family => ({ family, year: 2027, status: 'live', current_count: 5,
  point_estimate: 10, ci_lower: 8, ci_upper: 12, event_start: '2027-01-01', days_remaining: 50 });
async function load(events) {
  reply = { ok: true, json: async () => ({ events }) };
  await run("loadEntryValues('synthetic-key')");
}
async function main() {
  run('_syncValueUi(); renderAllTournaments()');
  assert.equal(node('thValue').hidden, true);
  assert.equal(node('thActual').hidden, true);
  context.TOURNAMENT_DATA.tournaments = ['A', 'B', 'C'].map(card);
  await load([event('A', 25025, 1000, { last_day: { value: 12.5, span: 1 } }), event('B', 0, 2000), event('C', null, 3000)]);
  assert.equal(node('thValue').hidden, false);
  assert.equal(node('thActual').hidden, false);
  const actual = run("actualValueCell({family:'A', year:2027})");
  assert.match(actual, /data-label="Actual so far"/);
  assert.match(actual, /\$250\.25/);
  assert.match(actual, /aria-label="\$250\.25\. Recorded Chess Action receipts/);
  assert.doesNotMatch(actual, /\$1,000/);
  assert.match(actual, /after recorded refunds/);
  assert.match(actual, /2026-11-12/);
  assert.match(actual, /\+\$12\.5 last day/);
  assert.doesNotMatch(run("valueCell({family:'A', year:2027})"), /last day/);
  assert.match(run("valueCell({family:'A', year:2027})"), /\$1,000/);
  assert.match(run("valueCell({family:'A', year:2027})"), /aria-label="\$1,000\. Expected final Chess Action receipts/);
  assert.match(run("actualValueCell({family:'B', year:2027})"), /\$0\.00/);
  assert.doesNotMatch(run("actualValueCell({family:'C', year:2027})"), /\$/);
  assert.equal((node('tourneyBody').innerHTML.match(/data-label="Actual so far"/g) || []).length, 3);
  // Actual ordering differs from expected ordering; unavailable stays last both ways.
  const order = () => [...node('tourneyBody').innerHTML.matchAll(/class="t-name"[^>]*>([^<]+)/g)].map(m => m[1]);
  run("sortTable('actual')");
  assert.deepEqual(order(), ['B', 'A', 'C']);
  run("sortTable('actual')");
  assert.deepEqual(order(), ['A', 'B', 'C']);
  run("sortTable('value')");
  assert.deepEqual(order(), ['A', 'B', 'C']);
  for (const header of headers) assert.equal(header.getAttribute('tabindex'), '0');
  const keySort = (target, key) => {
    let prevented = false;
    for (const handler of listeners.get('keydown')) handler({ target, key, preventDefault() { prevented = true; } });
    assert.equal(prevented, true);
  };
  keySort(headers[1], 'Enter');
  assert.deepEqual(order(), ['B', 'A', 'C']);
  assert.equal(headers[1].getAttribute('aria-sort'), 'ascending');
  keySort(headers[1], ' ');
  assert.deepEqual(order(), ['A', 'B', 'C']);
  assert.equal(headers[1].getAttribute('aria-sort'), 'descending');
  keySort(headers[0], 'Enter');
  assert.equal(headers[0].getAttribute('aria-sort'), 'ascending');
  assert.equal(headers[1].getAttribute('aria-sort'), null);
  await load([event('A', 25025, 1000, { last_day: { value: -10, span: 3 } })]);
  assert.match(run("actualValueCell({family:'A', year:2027})"), /−\$10 \/ 3d/);
  assert.doesNotMatch(run("valueCell({family:'A', year:2027})"), /−\$10|3d/);
  for (const last_day of [null, { value: 0, span: 1 }, { value: NaN, span: 1 }]) {
    await load([event('A', 25025, 1000, { last_day })]);
    assert.doesNotMatch(run("actualValueCell({family:'A', year:2027})"), /last day|td-value-sub/);
  }
  for (const invalid of [null, undefined, -1, 1.5, '25025', Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    await load([event('A', invalid, 1000, { last_day: { value: 12.5, span: 1 } })]);
    assert.doesNotMatch(run("actualValueCell({family:'A', year:2027})"), /\$/);
  }
  await load([event('A', 25025, null, { missing: 'no_history', last_day: { value: 12.5, span: 1 } })]);
  assert.match(run("actualValueCell({family:'A', year:2027})"), /\$250\.25/);
  assert.match(run("actualValueCell({family:'A', year:2027})"), /\+\$12\.5 last day/);
  await load([event('A', 25025, 1000, { stale: true, missing: 'collection_failed', last_day: { value: 12.5, span: 1 } })]);
  assert.match(run("actualValueCell({family:'A', year:2027})"), /stale/);
  assert.match(run("actualValueCell({family:'A', year:2027})"), /refresh needed/);
  assert.doesNotMatch(run("actualValueCell({family:'A', year:2027})"), /last day/);
  await load([event('A', 25025, 1000, { basis: 'onsite' })]);
  assert.doesNotMatch(run("actualValueCell({family:'A', year:2027})"), /\$/);
  assert.match(run("valueCell({family:'A', year:2027})"), /\$1,000/);
  assert.doesNotMatch(run("actualValueCell({family:'unknown', year:2027})"), /\$/);
  reply = { ok: false, status: 401 };
  await run("loadEntryValues('synthetic-key')");
  assert.equal(node('thValue').hidden, true);
  assert.equal(node('thActual').hidden, true);
  assert.doesNotMatch(node('tourneyBody').innerHTML, /data-label="Actual so far"|data-label="Expected"/);
  assert.equal(node('valueMsg').textContent, 'Wrong key.');
  await load([event('A', 25025)]);
  assert.equal(node('thActual').hidden, false);
  console.log(JSON.stringify({ expected_preserved: true, actual_cents: true, zero_missing_stale: true,
    independent_sort: true, legacy_unavailable: true, unlock_failure_retry: true }));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
