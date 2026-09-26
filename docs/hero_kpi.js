// hero_kpi.js — the hero cell: the label, the figure under the highlighter,
// the range bracket and its tags. hero_figures.js draws the three figures and
// the week's bars; the favorites live at the foot of this file.

// ══════════════════════════════════════════════════════════
// HERO + KPI
// ══════════════════════════════════════════════════════════

// Build the prediction-tile tooltip from live PERFORMANCE_SUMMARY so every
// pipeline run (daily auto_update + monthly recalibration) refreshes the
// numbers automatically. No hardcoded counts/biases.
function _calibrationTooltip() {
  const fallback = 'Ensemble of pace-ratio extrapolation + family regression. At T > 7 the regression dominates so early ahead-of-pace leads are discounted.';
  if (typeof PERFORMANCE_SUMMARY === 'undefined' || !PERFORMANCE_SUMMARY) return fallback;
  const yr = String(new Date().getFullYear());
  const yearData = (PERFORMANCE_SUMMARY.years || {})[yr] || PERFORMANCE_SUMMARY;
  const agg = yearData.aggregate || PERFORMANCE_SUMMARY.aggregate || [];
  if (!agg.length) return fallback;
  // n-weighted mean of |bias_pct| across T-points: how much the model
  // typically over- or under-shoots in the current year.
  let nSum = 0, biasNum = 0;
  for (const a of agg) {
    if (typeof a.bias_pct === 'number' && typeof a.n === 'number') {
      biasNum += a.bias_pct * a.n;
      nSum += a.n;
    }
  }
  const meanBias = nSum > 0 ? biasNum / nSum : null;
  const nEvents = yearData.n_tournaments ?? PERFORMANCE_SUMMARY.n_tournaments ?? null;
  const asof = PERFORMANCE_SUMMARY.generated || '';
  if (meanBias == null || nEvents == null) return fallback;
  const dir = meanBias > 0 ? 'over-predicting' : 'under-predicting';
  const absBias = Math.abs(meanBias).toFixed(1);
  return `Ensemble of pace-ratio extrapolation + family regression. At T > 7 the regression dominates so early ahead-of-pace leads are discounted. ${yr} backtest (${nEvents} events, asof ${asof}) shows the model has been ${dir} by ${absBias}% on avg; kept conservative on purpose. See Performance tab for full breakdown.`;
}

// The hero cell (forecast.css): the label, the figure under the highlighter,
// the range bracket with its tags, the festival cluster, the week's bars and
// the three figures. renderProgress (panels_info.js) folds the progress
// lines into the first two figures after this runs.
function renderHero(t) {
  const done = isDone(t);
  _renderHeroFigure(t, done);
  document.getElementById('heroCi').innerHTML = _heroRangeHTML(t, done);
  // The pace verdict is the note above and the 7-day pace is a figure below;
  // the narrative would say it a third time.
  document.getElementById('heroNarrative').innerHTML = '';
  // Festival cluster — renders inline if this tournament is part of a
  // multi-sub-event festival (e.g. World Open). No-op otherwise.
  renderFestivalCluster(t);
  _renderHeroFigures(t, done);
  _renderKpiProgress(t, done);
  _renderWeekBars(t, done);
}

const HERO_HELP_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>';

function _renderHeroFigure(t, done) {
  const statusPrefix = t.status === 'historical' ? `${t.year} ` : '';
  const heroLabel = document.getElementById('heroLabel');
  if (done) {
    heroLabel.textContent = `${statusPrefix}Final Entries`;
  } else {
    heroLabel.innerHTML = `Predicted Final Entries <span class="hero-help" title="${esc(_calibrationTooltip())}">${HERO_HELP_ICON}</span>`;
  }
  const heroNum = document.getElementById('heroNumber');
  // A forecast sits under the highlighter; a final count is a fact in ink.
  heroNum.classList.toggle('hero-number-final', done);
  const target = t.point_estimate;
  // #heroNumber is aria-hidden and the tween writes it every frame; the value
  // reaches assistive tech once, from this dedicated live region, with the
  // label included so the number is not announced bare (2026-09-07 review).
  const announce = document.getElementById('heroAnnounce');
  if (announce) announce.textContent = `${heroLabel.textContent.trim()}: ${fmt(Math.round(target))}`;
  // Animate the count-up (skip the tween under prefers-reduced-motion)
  if (_reduceMotion()) { heroNum.textContent = fmt(Math.round(target)); return; }
  const duration = 600;
  const start = performance.now();
  (function animHero(now) {
    const p = Math.min(((now || performance.now()) - start) / duration, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    heroNum.textContent = fmt(Math.round(target * ease));
    if (p < 1) requestAnimationFrame(animHero);
  })(performance.now());
}

// The confidence and the prediction tier, printed as tags.
function _heroTags(t, done) {
  // Audit telemetry: prefer the explicit low_confidence flag over the derived
  // nHist count. n_historical_editions is the audit-canonical count (excludes
  // COVID/online); the historical array length is the fallback.
  const nHist = (typeof t.n_historical_editions === 'number')
    ? t.n_historical_editions
    : (t.historical ? t.historical.length : 0);
  const isLow = (typeof t.low_confidence === 'boolean') ? t.low_confidence : (nHist < 4);
  const confLabel = isLow
    ? (nHist >= 2 ? 'Low Confidence' : 'Very Low Confidence')
    : (nHist >= 8 ? 'High Confidence' : 'Medium Confidence');
  const confClass = isLow ? 'tag-ember' : (nHist >= 8 ? 'tag-signal' : 'tag-ink');
  const conf = !done && t.ci_lower !== t.ci_upper
    ? `<span class="tag ${confClass}" title="${nHist} qualifying historical edition${nHist === 1 ? '' : 's'} for this family. Below 4 editions, the model marks the prediction low-confidence.">${confLabel} · ${nHist} Edition${nHist === 1 ? '' : 's'}</span>`
    : '';
  // The fallback tier, when the prediction did not use direct family ratios.
  const tierLabelMap = {
    'family-direct': 'Direct · 5+ Yr History',
    'family-alias': 'Family Alias · Pooled History',
    'size-matched': 'Size Matched · No Family History',
    'roster-pending': 'Interim · Not in Roster Yet',
  };
  const tier = (!done && t.prediction_tier && t.prediction_tier !== 'family-direct')
    ? `<span class="tag" title="Prediction used the '${t.prediction_tier}' fallback path. 'family-alias' pools history from related families; 'size-matched' uses families with comparable historical size when this family has no direct history.">${tierLabelMap[t.prediction_tier] || t.prediction_tier.replace('-', ' ')}</span>`
    : '';
  return conf + tier;
}

// Why the model is as confident as it is, in one sentence.
function _confidenceReason(t) {
  const conf = (t.confidence_label || '').toLowerCase();
  const tier = (t.prediction_tier || 'family-direct').toLowerCase();
  if (tier === 'family-direct' && conf.includes('high')) return 'Strong prior data: 5+ years of same-month history for this family.';
  if (tier === 'family-direct' && conf.includes('medium')) return 'Moderate prior data: 3–4 years of comparable history.';
  if (tier === 'family-direct' && conf.includes('low') && !conf.includes('very')) return 'Sparse prior data: under 3 comparable years.';
  if (conf.includes('very')) return 'Limited or no comparable history; estimate falls back to family average.';
  if (tier === 'family-alias') return 'No direct history: pooled from related families for this prediction.';
  if (tier === 'size-matched') return 'No family history: drawn from families with comparable historical size.';
  return `${t.confidence_label || 'Confidence'} based on ${tier.replace('-', ' ')} history.`;
}

// The 80% range as a bracket, the estimate's pen tick placed inside it. A
// completed tournament shows its final count instead.
function _heroRangeHTML(t, done) {
  const tags = _heroTags(t, done);
  if (t.ci_lower === t.ci_upper) {
    return `<span class="ci-final">${fmt(t.current_count)}</span> total entries<div class="hero-tags">${tags}</div>`;
  }
  const ciLevel = Math.round((t.ci_level || .8) * 100);
  const lo = t.ci_lower, hi = t.ci_upper, pe = t.point_estimate;
  // Clamp so an off-band point estimate (a rare model edge case) still lands inside the bracket.
  const pct = Math.max(0, Math.min(100, ((pe - lo) / (hi - lo)) * 100));
  const reason = _confidenceReason(t);
  return `
      <div class="range" role="img" aria-label="${ciLevel}% confidence interval from ${fmt(lo)} to ${fmt(hi)}, point estimate ${fmt(pe)}. ${reason}" title="${reason}">
        <span class="range-bound">${fmt(lo)}</span>
        <div class="range-track"><div class="range-mark" style="left:${pct.toFixed(2)}%" title="Point estimate: ${fmt(pe)}. ${reason}"></div></div>
        <span class="range-bound">${fmt(hi)}</span>
      </div>
      <div class="range-caption">Estimated final entries &middot; ${ciLevel}% range</div>
      <div class="hero-tags">${tags}</div>`;
}

// Apply any saved overrides on load
// ══════════════════════════════════════════════════════════
// FAVORITES (My Tournaments)
// ══════════════════════════════════════════════════════════
const FAV_KEY = 'cca_favorites';

function getFavorites() {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) { return []; }
}

function saveFavorites(favs) {
  localStorage.setItem(FAV_KEY, JSON.stringify(favs));
}

function isFavorite(family) {
  return getFavorites().includes(family);
}

function toggleFavorite(family) {
  const favs = getFavorites();
  const idx = favs.indexOf(family);
  if (idx >= 0) favs.splice(idx, 1);
  else favs.push(family);
  saveFavorites(favs);
  updateFavButton(family);
}

function toggleFavoriteSelected() {
  const t = TOURNAMENT_DATA.tournaments[selectedIndex];
  if (t) toggleFavorite(t.family);
}

function updateFavButton(family) {
  const btn = document.getElementById('favToggle');
  if (!btn) return;
  const fav = isFavorite(family);
  btn.innerHTML = `<svg viewBox="0 0 24 24" fill="${fav ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11.5 3.6a.6.6 0 0 1 1 0l2.3 4.8 5.2.8a.6.6 0 0 1 .3 1l-3.8 3.7.9 5.2a.6.6 0 0 1-.9.6L12 17.3l-4.6 2.5a.6.6 0 0 1-.9-.6l.9-5.2-3.8-3.7a.6.6 0 0 1 .3-1l5.2-.8Z"/></svg>`;
  btn.classList.toggle('fav-active', fav);
  btn.title = fav ? 'Remove from My Tournaments' : 'Add to My Tournaments';
}
