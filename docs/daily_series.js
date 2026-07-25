/**
 * daily_series.js — gap-safe reading of a tournament's daily_data curve.
 *
 * Audit v3 P1 (audit/AUDIT_2026-07-25.md). Around fourteen places in app.js
 * used to read daily_data by array position: the week bars counted backwards
 * from the generation date, the "today's change" chip took last-minus-prior,
 * and the main chart derived x-dates from the tail. All of that is correct only
 * while the series has one point per calendar day. It does not.
 *
 * When the 2026-07-22 scrape failed, the gap it left was rendered as a single
 * day's registrations — the visible "+125 entries yesterday" bar on Bradley
 * Open. The pipeline fix stops the corrupt values, but the client would still
 * mislabel the next missing day, so the defence belongs here too.
 *
 * Two ideas:
 *   1. Date points from their own day_from_start index against the exported
 *      daily_start_date anchor, never from their position in the array.
 *   2. Sanitise before drawing: drop points that exceed the scraped count,
 *      enforce monotonicity, and mark gaps so callers can label them honestly
 *      instead of silently averaging across them.
 */
(function (root) {
  'use strict';

  // A jump beyond this multiple of the prior point, on a series where the jump
  // also clears MIN_SUSPECT_COUNT, is treated as an artefact rather than real
  // registrations. Mirrors the pipeline's A4 detector so both halves agree.
  var SUSPECT_JUMP_RATIO = 3;
  var MIN_SUSPECT_COUNT = 50;

  /**
   * Normalise a raw daily_data array.
   *
   * @param {Array<Array<number>>} series  raw [day_from_start, cumulative] pairs
   * @param {Object} opts
   *   currentCount {number|null}  scraped entry total; caps the curve when known
   *   isLive       {boolean}      only live cards get the currentCount cap
   * @returns {{points: Array, dropped: number, capped: boolean}}
   */
  function sanitizeSeries(series, opts) {
    opts = opts || {};
    var out = { points: [], dropped: 0, capped: false };
    if (!Array.isArray(series) || series.length === 0) return out;

    var cc = (typeof opts.currentCount === 'number' && isFinite(opts.currentCount))
      ? opts.currentCount : null;

    var clean = [];
    var seenDays = Object.create(null);
    for (var i = 0; i < series.length; i++) {
      var pt = series[i];
      if (!Array.isArray(pt) || pt.length < 2) { out.dropped++; continue; }
      var day = Number(pt[0]);
      var val = Number(pt[1]);
      if (!isFinite(day) || !isFinite(val) || day < 0 || val < 0) { out.dropped++; continue; }
      // Duplicate day index: keep the higher cumulative reading.
      if (seenDays[day] !== undefined) {
        out.dropped++;
        if (val > seenDays[day]) seenDays[day] = val;
        continue;
      }
      seenDays[day] = val;
      clean.push([day, val]);
    }

    clean.sort(function (a, b) { return a[0] - b[0]; });
    for (var d in seenDays) clean.forEach(function (p) { if (p[0] === Number(d)) p[1] = seenDays[d]; });

    // A live card's curve cannot exceed the entries actually scraped. This is
    // the client-side mirror of the incident invariant: rather than drawing a
    // fabricated 625 against a real 197, drop the impossible points.
    var kept = [];
    for (var j = 0; j < clean.length; j++) {
      if (opts.isLive && cc !== null && clean[j][1] > cc) {
        out.dropped++;
        out.capped = true;
        continue;
      }
      // Cumulative totals only rise; a fall means a misassembled curve.
      if (kept.length && clean[j][1] < kept[kept.length - 1][1]) {
        out.dropped++;
        continue;
      }
      kept.push(clean[j]);
    }

    out.points = kept;
    return out;
  }

  /**
   * Calendar Date for one point, from its own day index.
   *
   * Anchored in UTC deliberately. These are calendar dates, not instants: the
   * day a registration landed does not change because the reader is in Berlin.
   * Parsing 'YYYY-MM-DD' as local time and formatting back through UTC shifts
   * the label by a day for anyone west of Greenwich, so the whole path stays on
   * UTC getters. Callers must format with getUTC* accessors — see fmtPointDate.
   *
   * Returns null when the card carries no daily_start_date anchor, so callers
   * can fall back rather than invent a date.
   */
  function pointDate(card, dayFromStart) {
    if (!card || !card.daily_start_date) return null;
    var base = new Date(card.daily_start_date + 'T00:00:00Z');
    if (isNaN(base.getTime())) return null;
    base.setUTCDate(base.getUTCDate() + Number(dayFromStart || 0));
    return base;
  }

  var DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  /** "Mon Jul 7" for a pointDate result, using UTC accessors. */
  function fmtPointDate(d) {
    if (!d || isNaN(d.getTime())) return '';
    return DAY_NAMES[d.getUTCDay()] + ' ' + MONTH_NAMES[d.getUTCMonth()] + ' ' + d.getUTCDate();
  }

  /**
   * Per-interval registration deltas with their true day spans.
   *
   * Each entry: {fromDay, toDay, span, added, perDay, isGap, date}
   * `span > 1` means the interval covers more than one calendar day, so callers
   * must not label `added` as a single day's registrations.
   */
  function intervals(card, opts) {
    opts = opts || {};
    var s = sanitizeSeries((card || {}).daily_data, {
      currentCount: (card || {}).current_count,
      isLive: opts.isLive !== undefined ? opts.isLive : ((card || {}).status === 'live'),
    });
    var pts = s.points;
    var res = [];
    for (var i = 1; i < pts.length; i++) {
      var span = pts[i][0] - pts[i - 1][0];
      var added = pts[i][1] - pts[i - 1][1];
      if (span <= 0) continue;
      res.push({
        fromDay: pts[i - 1][0],
        toDay: pts[i][0],
        span: span,
        added: added,
        perDay: added / span,
        isGap: span > 1,
        date: pointDate(card, pts[i][0]),
      });
    }
    return res;
  }

  /**
   * Registrations added on the most recent interval, but ONLY when that
   * interval really is one day. Returns null when the latest gap spans several
   * days — the caller must then say "over N days", not "today".
   *
   * This is the "+125 entries yesterday" bug reduced to one function: the old
   * code took last-minus-prior and called it today's change regardless of span.
   */
  function latestDailyChange(card, opts) {
    var iv = intervals(card, opts);
    if (!iv.length) return null;
    var last = iv[iv.length - 1];
    return last.span === 1 ? last.added : null;
  }

  /** Latest interval regardless of span, for callers that can label a range. */
  function latestInterval(card, opts) {
    var iv = intervals(card, opts);
    return iv.length ? iv[iv.length - 1] : null;
  }

  /**
   * Does the RAW series look like the incident shape — a suspiciously large
   * jump at the tail? Deliberately evaluated before the currentCount cap: the
   * cap removes the impossible point, so asking this question after sanitising
   * would always answer no, which is exactly the blindness that let the
   * fabricated Bradley Open curve ship. Callers use it to suppress
   * precise-sounding labels and to surface a data-quality note.
   */
  function hasSuspectTail(card) {
    var raw = sanitizeSeries((card || {}).daily_data, { isLive: false });
    var pts = raw.points;
    if (pts.length < 2) return false;
    var last = pts[pts.length - 1];
    var prior = pts[pts.length - 2];
    var added = last[1] - prior[1];
    if (added <= MIN_SUSPECT_COUNT) return false;

    // Impossible against the scraped total is suspect on its own.
    var cc = (card || {}).current_count;
    if (typeof cc === 'number' && isFinite(cc) && last[1] > cc) return true;

    // Otherwise: a jump more than SUSPECT_JUMP_RATIO times the prior level.
    return last[1] > prior[1] * SUSPECT_JUMP_RATIO;
  }

  var api = {
    sanitizeSeries: sanitizeSeries,
    pointDate: pointDate,
    fmtPointDate: fmtPointDate,
    intervals: intervals,
    latestDailyChange: latestDailyChange,
    latestInterval: latestInterval,
    hasSuspectTail: hasSuspectTail,
    SUSPECT_JUMP_RATIO: SUSPECT_JUMP_RATIO,
    MIN_SUSPECT_COUNT: MIN_SUSPECT_COUNT,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.DailySeries = api;
  }
})(typeof self !== 'undefined' ? self : this);
