// Node driver for docs/daily_series.js — exercised by tests/test_daily_series_js.py.
// Prints one JSON blob of results; the pytest side asserts on it. Keeps the
// browser module honest without needing a headless browser in CI.
const path = require('path');
const DS = require(path.join(__dirname, '..', '..', 'docs', 'daily_series.js'));

// The incident card, as it actually shipped: a real count of 197 with a curve
// that climbed to 625 across a gap where the 07-22 scrape was missing.
const incidentCard = {
  status: 'live',
  current_count: 197,
  daily_start_date: '2026-03-23',
  daily_data: [[0, 2], [10, 40], [20, 120], [24, 197], [28, 625]],
};

const healthyCard = {
  status: 'live',
  current_count: 200,
  daily_start_date: '2026-07-01',
  daily_data: [[0, 50], [1, 80], [2, 140], [3, 200]],
};

const gappyCard = {
  status: 'live',
  current_count: 300,
  daily_start_date: '2026-07-01',
  daily_data: [[0, 50], [1, 80], [8, 300]],
};

const messyCard = {
  status: 'live',
  current_count: 500,
  daily_start_date: '2026-07-01',
  daily_data: [[2, 140], [0, 50], [1, 80], [1, 90], [-4, 10], [3, 120], [4, 500]],
};

const out = {
  // The impossible 625 point must never reach a chart.
  incident_sanitized: DS.sanitizeSeries(incidentCard.daily_data, {
    currentCount: 197, isLive: true }),
  incident_latest_daily: DS.latestDailyChange(incidentCard),
  incident_suspect: DS.hasSuspectTail(incidentCard),

  healthy_latest_daily: DS.latestDailyChange(healthyCard),
  healthy_intervals: DS.intervals(healthyCard).map(i => ({
    span: i.span, added: i.added, isGap: i.isGap,
    date: i.date ? i.date.toISOString().slice(0, 10) : null })),

  // A 7-day gap must not be reported as one day's registrations.
  gappy_latest_daily: DS.latestDailyChange(gappyCard),
  gappy_latest_interval: (() => {
    const i = DS.latestInterval(gappyCard);
    return { span: i.span, added: i.added, perDay: i.perDay, isGap: i.isGap };
  })(),

  // Out-of-order, duplicate, negative-index and non-monotone points.
  messy_sanitized: DS.sanitizeSeries(messyCard.daily_data, {
    currentCount: 500, isLive: true }),

  // Dates come from the point's own index, not its array position.
  date_day0: DS.pointDate(healthyCard, 0).toISOString().slice(0, 10),
  date_day8: DS.pointDate(gappyCard, 8).toISOString().slice(0, 10),
  date_no_anchor: DS.pointDate({ daily_data: [] }, 3),

  empty_sanitized: DS.sanitizeSeries([], { currentCount: 10, isLive: true }),
  null_sanitized: DS.sanitizeSeries(null, { currentCount: 10, isLive: true }),
  empty_latest: DS.latestDailyChange({ status: 'live', daily_data: [] }),
};

process.stdout.write(JSON.stringify(out));
