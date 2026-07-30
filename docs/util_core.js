// util_core.js — shared date/curve/pace/staleness helpers, split verbatim
// from app.js (C1). Classic script: every top-level name is a page global
// by design. Load order is defined in index.html.

function fmt(n) { return n == null ? '–' : n.toLocaleString(); }
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
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
function fmtDateLong(s) {
  if (!s) return '–';
  const d = new Date(s + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}
function fmtDateTimeLong(iso) {
  if (!iso) return '–';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '–';
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit'
  });
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

// Builds the hero narrative — a 1-2 sentence plain-English summary that ties
// the headline numbers together. Returns HTML (not text) so we can highlight
// the specific phrase that's load-bearing (the comparison verdict) with
// color. Handles three states: completed (compare to historical avg),
// live with pace_alert (compare to N-yr at-T avg + name the next milestone),
// and live without pace_alert (still-loading or insufficient history).
function buildHeroNarrative(t) {
  if (!t) return '';
  // Completed: name what happened vs history.
  if (isDone(t)) {
    if (!t.historical || t.historical.length === 0) {
      return `<p>Final count: <strong>${fmt(t.current_count)}</strong> entries.</p>`;
    }
    const avg = Math.round(t.historical.reduce((s, h) => s + h.count, 0) / t.historical.length);
    const diff = t.current_count - avg;
    const pct = avg > 0 ? Math.round((diff / avg) * 100) : 0;
    let verdict, cls;
    if (pct >= 5) { verdict = `${Math.abs(pct)}% above`; cls = 'pos'; }
    else if (pct <= -5) { verdict = `${Math.abs(pct)}% below`; cls = 'neg'; }
    else { verdict = 'in line with'; cls = 'flat'; }
    return `<p><strong>${fmt(t.current_count)}</strong> entries: <span class="hn-verdict hn-${cls}">${verdict}</span> the ${t.historical.length}-year average of ${fmt(avg)}.</p>`;
  }

  // Live state — combine pace verdict + countdown + next milestone.
  const parts = [];
  const pa = t.pace_alert;
  if (pa && pa.expected != null) {
    const cls = pa.status === 'above_pace' ? 'pos'
              : pa.status === 'below_pace' ? 'neg' : 'flat';
    const dev = Math.round(pa.deviation_pct || 0);
    const devText = dev > 0 ? `+${dev}%` : `${dev}%`;
    const phrase = pa.status === 'on_pace'
      ? 'tracking on pace'
      : pa.status === 'above_pace'
        ? 'tracking ahead of pace'
        : 'tracking behind pace';
    parts.push(`<strong>${fmt(t.current_count)}</strong> of a predicted <strong>${fmt(t.point_estimate)}</strong>: <span class="hn-verdict hn-${cls}">${phrase} (${devText} vs prior years at the same days-to-event mark)</span>.`);
  } else {
    // No pace_alert (typically: not enough historical daily data).
    parts.push(`<strong>${fmt(t.current_count)}</strong> registered so far of a predicted <strong>${fmt(t.point_estimate)}</strong>.`);
  }

  // Daily pace + needed pace context.
  if (t.daily_data && t.daily_data.length >= 3 && t.days_remaining > 0) {
    const recent = t.daily_data.slice(-7);
    const daySpan = recent[recent.length-1][0] - recent[0][0];
    const regSpan = recent[recent.length-1][1] - recent[0][1];
    const rate = daySpan > 0 ? regSpan / daySpan : 0;
    const remaining = t.point_estimate - t.current_count;
    const needed = remaining / t.days_remaining;
    if (rate >= 0.5 && needed >= 0.5) {
      const verdict = rate >= needed * 0.95
        ? 'on track to land in the predicted range'
        : `needs ${needed.toFixed(1)}/day to hit the prediction (currently ${rate.toFixed(1)}/day)`;
      parts.push(verdict.charAt(0).toUpperCase() + verdict.slice(1) + '.');
    }
  }

  // Next milestone — the closest upcoming reference point.
  if (hasValidEarlyBird(t)) {
    const today = new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
    const ebDate = new Date(t.early_bird_deadline + 'T00:00:00');
    const ebDays = Math.ceil((ebDate - today) / 86400000);
    if (ebDays > 0 && ebDays <= 21) {
      parts.push(`Early bird closes in ${ebDays} day${ebDays === 1 ? '' : 's'}.`);
    }
  } else if (t.days_remaining != null && t.days_remaining <= 14 && t.days_remaining > 0) {
    const evStarted = t.event_start &&
      new Date(t.event_start + 'T00:00:00') <= new Date(TOURNAMENT_DATA.generated + 'T00:00:00');
    parts.push(evStarted
      ? `Online registration closes in ${t.days_remaining} day${t.days_remaining === 1 ? '' : 's'}.`
      : `Event opens in ${t.days_remaining} day${t.days_remaining === 1 ? '' : 's'}.`);
  }

  return `<p>${parts.join(' ')}</p>`;
}
function paceBadgeHTML(alert) {
  if (!alert) return '';
  const cls = alert.status === 'above_pace' ? 'above' : alert.status === 'below_pace' ? 'below' : 'on';
  const icon = alert.status === 'above_pace' ? '\uD83D\uDFE2' : alert.status === 'below_pace' ? '\uD83D\uDD34' : '\uD83D\uDFE1';
  return `<span class="pace-badge ${cls}">${icon}</span>`;
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
  globalThis.buildHeroNarrative = buildHeroNarrative;
  globalThis.paceBadgeHTML = paceBadgeHTML;
  globalThis.STALE_AFTER_HOURS = STALE_AFTER_HOURS;
  globalThis.assessDataFreshness = assessDataFreshness;
}
if (typeof module !== 'undefined') {
  module.exports = {
    fmt, isDone, EARLY_BIRD_MIN_GAP_DAYS, hasValidEarlyBird,
    fmtDate, fmtDateLong, fmtDateTimeLong, addDays, daysBetween,
    interpCurve, getPaceAlert, buildHeroNarrative, paceBadgeHTML,
    STALE_AFTER_HOURS, assessDataFreshness,
  };
}
