const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const root = path.join(__dirname, '../..');
const nodes = new Map();
const node = id => {
  if (!nodes.has(id)) nodes.set(id, { textContent: '', innerHTML: '', value: '', setAttribute() {}, getContext: () => ({}), parentNode: { appendChild() {} }, style: {}, classList: { toggle() {} } });
  return nodes.get(id);
};
const frames = [];
const context = vm.createContext({ console, performance: { now: () => 0 },
  document: { getElementById: node, createElement: () => ({className: '',textContent: ''}), querySelectorAll: () => [] }, requestAnimationFrame: f => frames.push(f),
  _reduceMotion: () => false, esc: s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
  selectedIndex: 0, _mobileVP: () => false,
  localStorage: { getItem: () => '[0,1]', setItem() {} },
  TOURNAMENT_DATA: { generated: '2026-11-10', counts_through: '2026-11-09' },
});
for (const file of ['util_core.js', 'chart_data.js', 'hero_kpi.js', 'panels_info.js', 'season_cards.js', 'email_compose.js', 'tab_compare.js', 'compare_chart.js', 'perf_live.js', 'panels_grid.js', 'chart_main.js', 'chart_hist.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'docs', file), 'utf8'), context, { filename: file });
}
const unavailable = { family: 'Example <Open>', year: 2027, status: 'live', current_count: 3,
  point_estimate: null, ci_lower: null, ci_upper: null, days_remaining: 142, event_start: '2027-04-01',
  daily_data: [[0, 1], [1, 3]], daily_start_date: '2026-11-08', registration_curve: [], historical: [] };
context.unavailable = unavailable;
vm.runInContext(`
  _renderHeroFigure({ ...unavailable, point_estimate: 100 }, false);
  _renderHeroFigure(unavailable, false);
`, context);
for (const f of frames) f(600);
assert.equal(node('heroNumber').textContent, '–');
assert.equal(node('heroLabel').textContent, 'Forecast unavailable');
assert.match(node('heroAnnounce').textContent, /Forecast unavailable/);
assert.match(vm.runInContext('_heroRangeHTML(unavailable, false)', context), /No completed editions/);
vm.runInContext('renderProgress(unavailable); renderMilestones(unavailable)', context);
assert.equal(node('kpiCurrentFold').innerHTML, '');
assert.equal(node('milestoneStrip').innerHTML, '');
const card = vm.runInContext("seasonCard({t: unavailable, i: 0}, 'select-tournament')", context);
assert.match(card, /3 registered/); assert.match(card, /forecast unavailable/);
assert.doesNotMatch(card, /rule-bar-fill/);
assert.match(card, /aria-label="[^"]*3 registered; forecast unavailable/);
for (const length of ['short', 'medium', 'long']) {
  context.length = length;
  const text = vm.runInContext('emailFormatTournament(unavailable, length)', context);
  const html = vm.runInContext('emailHTMLTournament(unavailable, length)', context);
  assert.match(text, /3 entries.*Forecast unavailable/);
  assert.match(html, /&lt;Open&gt;/); assert.doesNotMatch(html, /Example <Open>/);
  assert.doesNotMatch(text + html, /null|projects to 0|range of 0/);
}
context.zero = {...unavailable, current_count: 0, point_estimate: 0};
vm.runInContext('renderProgress(zero); _renderHeroFigure(zero, false)', context);
assert.doesNotMatch(node('kpiCurrentFold').innerHTML, /NaN|Infinity/);
assert.equal(node('heroNumber').textContent, '0');
assert.match(vm.runInContext('_compareLabel([{t: zero}])', context), /forecast 0/);
assert.doesNotMatch(vm.runInContext('_compareLabel([{t: zero}])', context), /unavailable|NaN|Infinity/);
const compare = vm.runInContext('_compareLabel([{t: unavailable}])', context);
assert.match(compare, /3 registered; forecast unavailable/); assert.doesNotMatch(compare, /finished/);
assert.match(vm.runInContext('emailOverallTheme([unavailable])', context), /Forecasts unavailable/);
const chartConfigs = [];
context.Chart = class { constructor(ctx, config) { chartConfigs.push(config); } destroy() {} };
context.Chart.Interaction = { modes: {} }; context.Chart.Tooltip = { positioners: {} };
Object.assign(context, { chart: null, _chartWindowState: null, themeRgba: x => x,
  PALETTE: { bg: '#fff', series: ['blue','red','black'], seriesDim: ['blue','red','black'] }, chartDescribe: (el, description) => { el.description = description; },
  chartAxisTitle: x => ({text: x}), chartTicks: x => x || {}, chartGridX: () => ({}), chartGridY: () => ({}),
  chartBorderX: () => ({}), chartBorderY: () => ({}), chartTooltip: x => x,
  makeVertMarkersPlugin: () => ({}), _chartWindow: () => ({min: 0, max: 1}), _chartTimeUnit: () => ({}),
  _syncChartRangeSeg() {}, weeklyStops: () => [], _syncLikelyRangeTitle() {},
  entryValueOn: () => false, entryValueFor: () => null });
vm.runInContext('renderChart(unavailable)', context);
assert.equal(chartConfigs.at(-1).data.datasets.map(d => d.label).join('|'), 'Actual Entries|Actual Points');
assert.doesNotMatch(node('chartLegend').innerHTML, /Projected|Range/);
assert.match(node('mainChart').description.label, /3 registered; forecast unavailable/);
vm.runInContext('renderCompareChart([{t: unavailable}, {t: zero}])', context);
assert.match(node('compareChart').description.label, /zero forecast/);
context.supported = {...unavailable, family: 'Supported Open', point_estimate: 6, ci_lower: 4, ci_upper: 8};
vm.runInContext('renderCompareChart([{t: unavailable}, {t: supported}])', context);
assert.ok(chartConfigs.at(-1).data.datasets.length > 0);
assert.ok(chartConfigs.at(-1).data.datasets.every(d => !d.label.includes('Example')));
assert.match(node('compareChart').description.label, /forecast unavailable/);
vm.runInContext('renderCompareChart([{t: zero}, {t: supported}])', context);
assert.match(node('compareChart').description.label, /forecast 0/);
assert.ok(chartConfigs.at(-1).data.datasets.every(d => !d.label.includes('Example')));
for (const col of ['predicted', 'progress']) for (const dir of ['asc', 'desc']) {
  context.sortCol = col; context.sortDir = dir;
  vm.runInContext('TOURNAMENT_DATA.tournaments=[unavailable,supported]; tableSortCol=sortCol; tableSortDir=sortDir; renderAllTournaments()', context);
  const rows = node('tourneyBody').innerHTML;
  assert.ok(rows.indexOf('Supported Open') < rows.indexOf('Example &lt;Open&gt;'));
  assert.match(rows, /Unavailable/);
}
vm.runInContext(`
  TOURNAMENT_DATA.tournaments = [unavailable, {...unavailable, family: 'Other Open'}];
  renderCompareTab();
`, context);
assert.match(node('compareContent').innerHTML, /Unavailable/);
vm.runInContext('TOURNAMENT_DATA.tournaments = [{...zero, ci_lower: 0, ci_upper: 0}, supported]; renderCompareTab()', context);
assert.match(node('compareContent').innerHTML, /0 – 0/);
assert.equal(vm.runInContext('emailComputeHighlights([{...zero, historical: [{year: 2026, count: 10}]}]).biggestDown.pct', context), -1);
assert.doesNotMatch(node('compareContent').innerHTML, /predicted [0-9]+% higher/);
context.periodData = { live_record: { n_records: 0, evaluation_periods: [
  {label: 'Original evaluation', archived_on: '2026-11-10', results: { n_records: 16, n_events: 4, frozen_on: '2026-09-27', pooled: {} }},
  {label: 'Current evaluation', results: { n_records: 0, frozen_on: '2026-11-10' }},
]}};
vm.runInContext('perfDrawLive(periodData)', context);
assert.match(node('perfLive').innerHTML, /Original evaluation: 16 forecasts/);
assert.match(node('perfLive').innerHTML, /Current evaluation: frozen on 2026-11-10/);
assert.match(node('perfLive').innerHTML, /No finished events have graded forecasts yet/);

context.proxy = {...context.supported, historical: [{year: 2025,count:25,source_section:'Young Adult/Middle Age',source_family:'Predecessor'}], n_historical_editions:1, low_confidence:true, history_basis:'transferred_sections', history_note:'Based on prior Young Adult/Middle Age sections; 2027 rules differ.'};
assert.match(vm.runInContext('_heroRangeHTML(proxy, false)', context), /historical observation/);
assert.match(vm.runInContext('_heroRangeHTML(proxy, false)', context), /2027 rules differ/);
context.hostileProxy = {...context.proxy, history_note:'<img src=x> " title="foreign'};
const escapedBasis=vm.runInContext('_heroRangeHTML(hostileProxy, false)', context);
assert.doesNotMatch(escapedBasis, /<img/);
assert.doesNotMatch(escapedBasis.slice(0,escapedBasis.indexOf('>')), /title="foreign/);
assert.match(escapedBasis, /&lt;img/);assert.match(escapedBasis,/&quot;/);
assert.equal(vm.runInContext('historySlots(proxy.historical,{year:2027,count:6})[0].label', context), '2025 section');
for (const length of ['short','medium','long']) {
 context.length=length;
 const text=vm.runInContext('emailFormatTournament(proxy,length)',context);
 const html=vm.runInContext('emailHTMLTournament(proxy,length)',context);
 assert.match(text,/prior Young Adult\/Middle Age sections/);assert.match(html,/prior Young Adult\/Middle Age sections/);
 assert.doesNotMatch(text+html,/Last year was|last year we|finished at/);
}

context.proxySelection = [context.proxy, {...context.proxy, family:'Other proxy'}];
assert.equal(vm.runInContext('emailOverallTheme(proxySelection)',context),'');
for (const length of ['medium','long']) {
 context.length=length;
 const html=vm.runInContext("emailBuildHTML('Subject','',proxySelection,length,{biggestUp:null,biggestDown:null,fastestPace:null,behindPace:[]},'')",context);
 assert.doesNotMatch(html,/holding steady|improvement across|lagging across/);
 assert.match(html,/prior Young Adult\/Middle Age sections/);
}
context.directHistory = {...context.supported,historical:[{year:2026,count:6}]};
assert.match(vm.runInContext('emailOverallTheme([proxy,directHistory])',context),/^Among events with comparable prior editions,/);
assert.equal(vm.runInContext('emailOverallTheme([directHistory])',context),'Things are holding steady across the board.');
Object.assign(context,{histChartObj:null});
vm.runInContext('_avgPad=()=>0;renderHistorical(proxy)',context);
assert.equal(chartConfigs.at(-1).options.plugins.tooltip.callbacks.title([{dataIndex:0}]),'2025 section');
assert.equal(node('histChart').description.columns[0],'Year / section');
assert.match(node('histChart').description.caption,/prior section counts/);
assert.match(node('histNote').innerHTML,/2027 rules differ/);
console.log(JSON.stringify({ hero: true, animation_switch: true, progress: true, milestones: true,
  card: true, email_lengths: 3, escaped_html: true, comparison: true, main_chart: true, mixed_comparison: true, sorting: true, zero_forecast: true, empty_periods: true }));
