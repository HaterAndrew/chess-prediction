// Node driver for docs/util_core.js — exercised by tests/test_util_core_js.py.
// Mirrors the daily_series driver pattern: run the real file under node, print
// one JSON blob of results, and let the pytest side assert on it. Keeps the
// shared date/curve/pace/staleness helpers honest without a headless browser.
const path = require('path');
const U = require(path.join(__dirname, '..', '..', 'docs', 'util_core.js'));

const curve = [
  { days_before: 90, cumulative_pct: 0.10 },
  { days_before: 30, cumulative_pct: 0.50 },
  { days_before: 0, cumulative_pct: 1.0 },
];

const out = {
  fmt_null: U.fmt(null),
  fmt_num: U.fmt(12345),
  isdone_complete: U.isDone({ status: 'complete' }),
  isdone_historical: U.isDone({ status: 'historical' }),
  isdone_live: U.isDone({ status: 'live' }),

  days_between: U.daysBetween('2026-07-01', '2026-07-31'),
  add_days: (() => {
    const d = U.addDays('2026-07-01', 30);
    return [d.getFullYear(), d.getMonth() + 1, d.getDate()];
  })(),
  fmt_date_empty: U.fmtDate(null),
  fmt_datetime_bad: U.fmtDateTimeLong('not-a-date'),

  // Linear interpolation on the registration curve, plus the clamps.
  interp_above: U.interpCurve(curve, 120),
  interp_below: U.interpCurve(curve, -5),
  interp_mid: U.interpCurve(curve, 60),
  interp_empty: U.interpCurve([], 10),

  // Early-bird validity: needs a real price hike AND a 14+ day gap.
  eb_valid: U.hasValidEarlyBird({
    early_bird_deadline: '2026-07-01', event_start: '2026-08-01',
    early_bird_fee: 90, regular_fee: 110 }),
  eb_short_gap: U.hasValidEarlyBird({
    early_bird_deadline: '2026-07-29', event_start: '2026-08-01',
    early_bird_fee: 90, regular_fee: 110 }),
  eb_no_hike: U.hasValidEarlyBird({
    early_bird_deadline: '2026-07-01', event_start: '2026-08-01',
    early_bird_fee: 110, regular_fee: 110 }),
  eb_missing_fields: U.hasValidEarlyBird({ event_start: '2026-08-01' }),

  // Staleness: the browser clock must be able to overrule the baked flag.
  fresh: U.assessDataFreshness(
    { generated_time: '2026-07-30T00:00:00Z' },
    new Date('2026-07-30T12:00:00Z')),
  aged_out: U.assessDataFreshness(
    { generated: '2026-07-25' }, new Date('2026-07-30T12:00:00Z')),
  flagged: U.assessDataFreshness(
    { is_stale: true, generated_time: '2026-07-30T00:00:00Z' },
    new Date('2026-07-30T01:00:00Z')),
  degraded: U.assessDataFreshness(
    { pipeline_degraded: true, generated_time: '2026-07-30T00:00:00Z' },
    new Date('2026-07-30T01:00:00Z')),
  empty_freshness: U.assessDataFreshness(null, new Date('2026-07-30T00:00:00Z')),
  stale_after_hours: U.STALE_AFTER_HOURS,

  pace_alert: U.getPaceAlert({ pace_alert: { status: 'above_pace' } }),
  pace_alert_none: U.getPaceAlert({}),
  pace_badge_empty: U.paceBadgeHTML(null),
};
process.stdout.write(JSON.stringify(out));
