// util_core.js — shared date/curve/pace/staleness helpers, split verbatim
// from app.js (C1). Classic script: every top-level name is a page global
// by design. Load order is defined in index.html.

// The sheet is set in en-US, so its dates and figures are formatted by hand.
// toLocaleDateString with an options object built a new Intl formatter per
// call (the first render made hundreds: 130 ms of the fold's task at 4x CPU
// throttle), and even one Intl.DateTimeFormat costs the ICU load, 60 ms at
// 4x, on the first-paint path. These tables cost nothing.
const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];
const WEEKDAYS_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
function _asDate(d) { return d instanceof Date ? d : new Date(d); }
function _clock(d) {
  const h = d.getHours(), m = d.getMinutes();
  return `${h % 12 || 12}:${m < 10 ? '0' : ''}${m} ${h < 12 ? 'AM' : 'PM'}`;
}
// Each entry formats like the Intl.DateTimeFormat of the same name did:
// short "Sep 26", long "September 26, 2026", weekdayLong "Sat, September 26",
// month "Sep", full "Sat, Sep 26, 2026", dateTime "Sep 26, 2026, 8:05 PM".
const DATE_FMT = {
  short: { format: d => { d = _asDate(d); return `${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}`; } },
  long: { format: d => { d = _asDate(d); return `${MONTHS_LONG[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`; } },
  weekdayLong: { format: d => { d = _asDate(d); return `${WEEKDAYS_SHORT[d.getDay()]}, ${MONTHS_LONG[d.getMonth()]} ${d.getDate()}`; } },
  month: { format: d => MONTHS_SHORT[_asDate(d).getMonth()] },
  full: { format: d => { d = _asDate(d); return `${WEEKDAYS_SHORT[d.getDay()]}, ${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`; } },
  dateTime: { format: d => { d = _asDate(d); return `${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}, ${_clock(d)}`; } }
};
// Thousands separators on the integer part, the way en-US toLocaleString
// grouped them; decimals stay as given.
function fmt(n) {
  if (n == null) return '–';
  if (typeof n !== 'number') return String(n);
  const neg = n < 0 ? '-' : '';
  const [whole, frac] = String(Math.abs(n)).split('.');
  return neg + whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (frac ? '.' + frac : '');
}
function isDone(t) { return t.status === 'complete' || t.status === 'historical'; }

// An "early bird" only exists when there's an actual price hike BETWEEN an
// early-bird window and a regular window, AND the deadline lands well before
// the event. Just having a deadline isn't enough — many CCA events publish a
// $X advance / $X+ onsite step 2-3 days out (Cleveland Open 2026: $93→$110
// with 3d gap), which is a late-registration penalty, not an early bird.
// Threshold: at least 14 days between early_bird_deadline and event_start.
// CCA metadata also occasionally carries impossible deadlines (e.g. Chicago
// Class 2026 had EB=Nov 10 with event=Jul 17), which the gap check excludes.
const EARLY_BIRD_MIN_GAP_DAYS = 14;
function hasValidEarlyBird(t) {
  if (!t.early_bird_deadline || !t.event_start) return false;
  if (t.early_bird_fee == null || t.regular_fee == null) return false;
  if (t.early_bird_fee >= t.regular_fee) return false;
  return daysBetween(t.early_bird_deadline, t.event_start) >= EARLY_BIRD_MIN_GAP_DAYS;
}
function fmtDate(s) {
  if (!s) return '–';
  const d = new Date(s + 'T00:00:00');
  return DATE_FMT.short.format(d);
}
function fmtDateLong(s) {
  if (!s) return '–';
  const d = new Date(s + 'T00:00:00');
  return DATE_FMT.long.format(d);
}
function fmtDateTimeLong(iso) {
  if (!iso) return '–';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '–';
  return DATE_FMT.dateTime.format(d);
}
function addDays(dateStr, days) {
  const d = new Date(dateStr + 'T00:00:00');
  d.setDate(d.getDate() + days);
  return d;
}
function daysBetween(a, b) {
  return Math.round((new Date(b + 'T00:00:00') - new Date(a + 'T00:00:00')) / 86400000);
}
function interpCurve(curve, daysBefore) {
  if (!curve || curve.length === 0) return 1;
  const sorted = [...curve].sort((a, b) => b.days_before - a.days_before);
  const pct = (pt) => pt.cumulative_pct !== undefined ? pt.cumulative_pct : (pt.pct || 0);
  if (daysBefore >= sorted[0].days_before) return pct(sorted[0]);
  if (daysBefore <= sorted[sorted.length-1].days_before) return pct(sorted[sorted.length-1]);
  for (let i = 0; i < sorted.length - 1; i++) {
    if (daysBefore <= sorted[i].days_before && daysBefore >= sorted[i+1].days_before) {
      const frac = (sorted[i].days_before - daysBefore) / (sorted[i].days_before - sorted[i+1].days_before);
      return pct(sorted[i]) + frac * (pct(sorted[i+1]) - pct(sorted[i]));
    }
  }
  return 1;
}

// ══════════════════════════════════════════════════════════
// PACE ALERT HELPERS
// ══════════════════════════════════════════════════════════
function getPaceAlert(t) {
  return t && t.pace_alert ? t.pace_alert : null;
}

// The multi-year at-T context (alert.message from alerts.py) used to render
// as its own separate banner below the YoY delta banner. Two stacked
// indicators competing for attention; the lightning-bolt one duplicated
// the parenthetical pct already inside the message ("(-1%)" + "-0.8%").
// Now it ships as a sub-line inside the delta banner via renderDelta().

// Hours after which baked data is treated as stale regardless of the flag the
// pipeline stamped. The scrape runs nightly, so anything past ~a day and a half
// means at least one run did not land. Audit v3 P2.
const STALE_AFTER_HOURS = 36;

/**
 * Decide whether the data on this page is stale, WITHOUT trusting the
 * server-baked is_stale flag on its own.
 *
 * Audit v3 P2/O1: `is_stale` is stamped by the last step of the pipeline, so a
 * run that dies before that step leaves the previous run's `false` in place.
 * That is exactly what happened on 2026-07-25 \u2014 the site served 07-24 data with
 * is_stale reading false and no banner. The browser's own clock is the one
 * signal a broken pipeline cannot forge, so age is computed here and either
 * source can raise the banner.
 *
 * Returns {stale, degraded, ageHours, reason}.
 */
function assessDataFreshness(data, now) {
  data = data || {};
  now = now || new Date();
  const flagged = Boolean(data.is_stale);
  const degraded = Boolean(data.pipeline_degraded);

  let ageHours = null;
  const raw = data.generated_time || data.generated;
  if (raw) {
    const gen = new Date(raw);
    if (!isNaN(gen.getTime())) {
      ageHours = (now.getTime() - gen.getTime()) / 36e5;
    }
  }
  // Negative age means the data claims to be from the future: a clock skew on
  // either side. Don't call that stale, but don't treat it as verified fresh.
  const tooOld = ageHours !== null && ageHours > STALE_AFTER_HOURS;

  return {
    stale: flagged || degraded || tooOld,
    degraded: degraded,
    ageHours: ageHours,
    reason: degraded ? 'degraded' : (flagged ? 'flagged' : (tooOld ? 'age' : null)),
  };
}

// ── UMD-style tail (added by the C1 split; not part of the original) ──
// In the browser the declarations above are already page globals (classic
// script, shared scope); mirroring them onto the root object is a no-op there
// but makes the same names reachable when this file is require()d by the node
// test driver (tests/js/util_core_driver.js).
if (typeof globalThis !== 'undefined') {
  globalThis.fmt = fmt;
  globalThis.isDone = isDone;
  globalThis.EARLY_BIRD_MIN_GAP_DAYS = EARLY_BIRD_MIN_GAP_DAYS;
  globalThis.hasValidEarlyBird = hasValidEarlyBird;
  globalThis.fmtDate = fmtDate;
  globalThis.fmtDateLong = fmtDateLong;
  globalThis.fmtDateTimeLong = fmtDateTimeLong;
  globalThis.addDays = addDays;
  globalThis.daysBetween = daysBetween;
  globalThis.interpCurve = interpCurve;
  globalThis.getPaceAlert = getPaceAlert;
  globalThis.STALE_AFTER_HOURS = STALE_AFTER_HOURS;
  globalThis.assessDataFreshness = assessDataFreshness;
}
if (typeof module !== 'undefined') {
  module.exports = {
    fmt, isDone, EARLY_BIRD_MIN_GAP_DAYS, hasValidEarlyBird,
    fmtDate, fmtDateLong, fmtDateTimeLong, addDays, daysBetween,
    interpCurve, getPaceAlert,
    STALE_AFTER_HOURS, assessDataFreshness,
  };
}
