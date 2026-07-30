// tab_ask.js — Ask-tab chatbot UI, split verbatim from app.js (C16).
// The ASK_* consts must be evaluated before app.js calls init() (a #ask
// deep link reaches initAskTab from init), hence this file loads earlier.
// The init() call itself stays at the tail of app.js.

// ══════════════════════════════════════════════════════════
// ASK TAB — chatbot UI
// (declarations must precede init() — init() may invoke initAskTab via
//  navigateToHash if the URL contains #ask, which would TDZ-throw on these
//  consts/lets if they're declared after init().)
// ══════════════════════════════════════════════════════════
const ASK_ENDPOINT = (function() {
  const h = (typeof location !== 'undefined') ? location.hostname : '';
  if (h === 'localhost' || h === '127.0.0.1' || h === '') return 'http://localhost:8787/ask';
  return 'https://chess-ask.hater-andrewd.workers.dev/ask';
})();
const ASK_SUGGESTIONS = [
  'When does Liberty Bell start?',
  'How big will Continental get?',
  'Top 5 biggest tournaments right now',
  'Did North American Open grow last year?',
  "What's the early bird fee for World Open?",
  'Which live tournament has the most entries?',
];
const ASK_HISTORY_KEY = 'cep:ask:history';
const ASK_MAX_HISTORY_PAIRS = 4;        // last N Q/A pairs sent as history[] (worker caps at 8 msgs)
const ASK_REQUEST_TIMEOUT_MS = 60000;   // client-side abort so a stuck request can't hang forever
// Query words that carry no signal for name matching in the keyword fallback.
const ASK_STOPWORDS = new Set(['the', 'a', 'an', 'of', 'in', 'on', 'at', 'for', 'to', 'is', 'are',
  'was', 'were', 'how', 'what', 'when', 'which', 'who', 'did', 'does', 'do', 'will', 'get', 'got',
  'and', 'or', 'vs', 'right', 'now', 'this', 'that', 'many', 'much', 'tournament', 'tournaments']);
let askInited = false;
let askInFlight = false;
let askController = null;                // AbortController for the in-flight request
const askTurns = [];                     // in-memory conversation ({q, a}) for multi-turn context

function initAskTab() {
  if (askInited) return;
  askInited = true;
  const info = document.getElementById('askDataInfo');
  if (info && typeof TOURNAMENT_DATA !== 'undefined' && TOURNAMENT_DATA && TOURNAMENT_DATA.generated) {
    info.textContent = `Plain English works. Data is current as of ${TOURNAMENT_DATA.generated}.`;
  }
  const chipsHost = document.getElementById('askChips');
  if (chipsHost) {
    chipsHost.innerHTML = '';
    ASK_SUGGESTIONS.forEach(q => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'ask-chip';
      b.textContent = q;
      b.addEventListener('click', () => askRun(q));
      chipsHost.appendChild(b);
    });
  }
  const input = document.getElementById('askInput');
  if (input) {
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        askSubmit();
      }
    });
  }
  const btn = document.getElementById('askSubmit');
  if (btn) {
    btn.addEventListener('click', askSubmit);
  }
  renderAskRecent();
}

function askSubmit() {
  if (askSubmit._busy) return;
  askSubmit._busy = true;
  setTimeout(() => { askSubmit._busy = false; }, 250);
  const input = document.getElementById('askInput');
  if (!input) return;
  let q = input.value.trim();
  if (!q) {
    q = ASK_SUGGESTIONS[0];
    input.value = q;
    showAskBanner('warn', 'Empty input: running the first suggestion. Type your own question and press Ask.');
  }
  askRun(q);
}

// Flatten the in-memory conversation into the worker's history[] shape (last N pairs).
function buildAskHistory() {
  const msgs = [];
  askTurns.slice(-ASK_MAX_HISTORY_PAIRS).forEach(p => {
    msgs.push({ role: 'user', content: p.q });
    msgs.push({ role: 'assistant', content: p.a });
  });
  return msgs;
}

async function askRun(question) {
  if (askInFlight) return;
  askInFlight = true;
  const input = document.getElementById('askInput');
  const btn = document.getElementById('askSubmit');
  const banner = document.getElementById('askBanner');
  if (input) input.value = '';
  if (btn) { btn.disabled = true; btn.textContent = 'Thinking…'; }
  if (banner) { banner.hidden = true; banner.textContent = ''; banner.className = 'ask-banner'; }

  appendUserTurn(question);
  const pending = appendAssistantPending();
  scrollAskThread();

  askController = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; askController.abort(); }, ASK_REQUEST_TIMEOUT_MS);

  try {
    const resp = await fetch(ASK_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history: buildAskHistory() }),
      signal: askController.signal,
    });
    const data = await resp.json().catch(() => ({}));
    pending.stop();

    if (!resp.ok) {
      const isRateLimit = resp.status === 429;
      const isBudget = resp.status === 503 && data.error === 'daily_budget_exhausted';
      const msg = data.message || `Error ${resp.status}.`;
      if (isRateLimit || isBudget) {
        showAskBanner('warn', msg);
        fillAssistantText(pending.bubble, '(No answer: ' + msg + ')');
      } else {
        showAskBanner('error', msg + ' Showing keyword matches instead.');
        fillAssistantFallback(pending.bubble, question);
      }
      return;
    }

    const answer = data.answer || '(no answer returned)';
    fillAssistantText(pending.bubble, answer, {
      model: data.model,
      latency_ms: data.latency_ms,
      data_generated: data.data_generated,
      tools_used: data.tools_used,
    });
    rememberAskTurn(question, answer);
    pushAskHistory(question);
  } catch (e) {
    pending.stop();
    if (e && e.name === 'AbortError') {
      if (timedOut) {
        fillAssistantText(pending.bubble, 'That took over a minute and was stopped. Try a simpler question, or these keyword matches:');
        fillAssistantFallback(pending.bubble, question, true);
      } else {
        fillAssistantText(pending.bubble, 'Stopped.');
      }
    } else {
      showAskBanner('error', 'AI is unavailable right now; here are keyword matches instead:');
      fillAssistantFallback(pending.bubble, question);
    }
  } finally {
    clearTimeout(timer);
    askController = null;
    askInFlight = false;
    if (btn) { btn.disabled = false; btn.textContent = 'Ask'; }
    scrollAskThread();
  }
}

function rememberAskTurn(q, a) {
  askTurns.push({ q, a });
  if (askTurns.length > 12) askTurns.shift();
}

function scrollAskThread() {
  const el = document.getElementById('askAnswer');
  if (!el) return;
  const last = el.lastElementChild;
  if (last && typeof last.scrollIntoView === 'function') {
    last.scrollIntoView({ block: 'nearest' });
  }
}

function appendUserTurn(text) {
  const host = document.getElementById('askAnswer');
  if (!host) return;
  const turn = document.createElement('div');
  turn.className = 'ask-turn ask-turn-user';
  const bubble = document.createElement('div');
  bubble.className = 'ask-bubble';
  bubble.textContent = text;
  turn.appendChild(bubble);
  host.appendChild(turn);
}

// Append an assistant bubble in the "thinking" state with an elapsed counter,
// a one-time SR announcement, and a Cancel button. Returns { bubble, stop() }.
function appendAssistantPending() {
  const host = document.getElementById('askAnswer');
  const turn = document.createElement('div');
  turn.className = 'ask-turn ask-turn-assistant';
  const bubble = document.createElement('div');
  bubble.className = 'ask-bubble ask-bubble-pending';

  const row = document.createElement('div');
  row.className = 'ask-pending';

  const spinner = document.createElement('span');
  spinner.className = 'ask-spinner';
  spinner.setAttribute('aria-hidden', 'true');

  // Constant text — announced once by the live region, not re-announced.
  const msg = document.createElement('span');
  msg.className = 'ask-pending-msg';
  msg.textContent = 'Working on your answer; this can take up to a minute.';

  // Per-second counter — hidden from the accessibility tree so it doesn't spam SR.
  const label = document.createElement('span');
  label.className = 'ask-pending-label';
  label.setAttribute('aria-hidden', 'true');

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'ask-cancel';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.addEventListener('click', () => { if (askController) askController.abort(); });

  const started = Date.now();
  const tick = () => { label.textContent = Math.round((Date.now() - started) / 1000) + 's'; };
  tick();

  row.appendChild(spinner);
  row.appendChild(msg);
  row.appendChild(label);
  row.appendChild(cancelBtn);
  bubble.appendChild(row);
  turn.appendChild(bubble);
  host.appendChild(turn);

  const iv = setInterval(tick, 1000);
  return { bubble, stop() { clearInterval(iv); } };
}

function fillAssistantText(bubble, text, meta) {
  if (!bubble) return;
  bubble.classList.remove('ask-bubble-pending');
  bubble.innerHTML = '';
  const body = document.createElement('div');
  body.textContent = text;
  bubble.appendChild(body);
  if (meta) {
    const m = document.createElement('div');
    m.className = 'ask-answer-meta';
    const parts = [];
    if (meta.model) parts.push(esc(meta.model));
    if (typeof meta.latency_ms === 'number') parts.push((meta.latency_ms / 1000).toFixed(1) + 's');
    if (meta.data_generated) parts.push('data: ' + esc(meta.data_generated));
    if (Array.isArray(meta.tools_used) && meta.tools_used.length) {
      parts.push('tools: ' + meta.tools_used.map(esc).join(', '));
    }
    m.innerHTML = parts.join(' &middot; ');
    bubble.appendChild(m);
  }
}

function showAskBanner(kind, message) {
  const banner = document.getElementById('askBanner');
  if (!banner) return;
  banner.hidden = false;
  banner.className = 'ask-banner is-' + kind;
  banner.textContent = message;
}

// Rank tournaments by keyword overlap with the query. Any-token match (not
// all-tokens) so a multi-word question still surfaces the relevant families;
// stopwords are dropped, exact and substring hits rank highest.
function fallbackMatches(query) {
  if (!TOURNAMENT_DATA || !TOURNAMENT_DATA.tournaments) return [];
  const q = query.toLowerCase().trim();
  const rawTokens = q.split(/[^a-z0-9]+/).filter(Boolean);
  const tokens = rawTokens.filter(t => t.length > 1 && !ASK_STOPWORDS.has(t));
  const useTokens = tokens.length ? tokens : rawTokens;   // stopword-only query still matches on rawTokens
  return TOURNAMENT_DATA.tournaments
    .map(t => {
      const name = (t.family + ' ' + t.year).toLowerCase();
      let s = 0;
      if (name === q) s = 1000;
      else if (q && name.includes(q)) s += 100;
      let hits = 0;
      useTokens.forEach(tok => { if (name.includes(tok)) { s += 12; hits++; } });
      if (hits && hits === useTokens.length) s += 20;     // bonus when every query token lands
      return { t, s };
    })
    .filter(x => x.s > 0)
    .sort((a, b) => b.s - a.s)
    .slice(0, 8)
    .map(x => x.t);
}

// Render keyword matches into an assistant bubble. `append` keeps any text
// already placed above (used when a timeout message precedes the matches).
function fillAssistantFallback(bubble, query, append) {
  if (!bubble) return;
  bubble.classList.remove('ask-bubble-pending');
  if (!append) bubble.innerHTML = '';
  const matches = fallbackMatches(query);
  if (matches.length === 0) {
    const none = document.createElement('div');
    none.textContent = 'No keyword matches in the local data.';
    bubble.appendChild(none);
    return;
  }
  const head = document.createElement('div');
  head.textContent = 'Keyword matches:';
  bubble.appendChild(head);
  const list = document.createElement('div');
  list.className = 'ask-fallback-results';
  matches.forEach(t => {
    const row = document.createElement('div');
    row.className = 'ask-fallback-item';
    const name = document.createElement('div');
    name.innerHTML = '<strong>' + esc(t.family + ' ' + t.year) + '</strong>';
    const meta = document.createElement('div');
    meta.className = 'meta';
    const bits = [];
    if (t.status) bits.push(esc(t.status));
    if (t.event_start) bits.push(esc(t.event_start));
    if (typeof t.current_count === 'number') bits.push(t.current_count.toLocaleString() + ' entries');
    else if (typeof t.point_estimate === 'number') bits.push('predicted ' + t.point_estimate.toLocaleString());
    meta.textContent = bits.join(' · ');
    row.appendChild(name);
    row.appendChild(meta);
    list.appendChild(row);
  });
  bubble.appendChild(list);
}

function loadAskHistory() {
  try {
    const raw = localStorage.getItem(ASK_HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}
function pushAskHistory(q) {
  let h = loadAskHistory().filter(x => x !== q);
  h.unshift(q);
  h = h.slice(0, 5);
  try { localStorage.setItem(ASK_HISTORY_KEY, JSON.stringify(h)); } catch {}
  renderAskRecent();
}
function renderAskRecent() {
  const host = document.getElementById('askRecent');
  if (!host) return;
  const h = loadAskHistory();
  host.innerHTML = '';
  if (!h.length) return;
  const title = document.createElement('div');
  title.className = 'ask-recent-title';
  title.textContent = 'Recent';
  host.appendChild(title);
  const list = document.createElement('div');
  list.className = 'ask-recent-list';
  h.forEach(q => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'ask-recent-item';
    b.textContent = q;
    b.onclick = () => askRun(q);
    list.appendChild(b);
  });
  host.appendChild(list);
}
