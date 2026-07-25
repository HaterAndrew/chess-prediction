/* Hotel room-block audit tab.
 *
 * Browser port of hotel_audit.py (the CLI in the repo root): merges the
 * public CCA entry list for an event (fetched through the worker's
 * /cca-entrylist proxy; the CSP blocks chessaction.com directly) with the
 * organizer's registration export (parsed locally: the file never leaves
 * the browser) and produces a three-sheet .xlsx (Audit List for the hotel,
 * Reference + Summary for the organizer) plus an on-page executive summary.
 *
 * Merge rules mirror hotel_audit.py exactly; the pytest parity gate
 * tests/test_audit_js_parity.py runs buildPeople under node against the
 * Python build_people on shared fixtures, so the two implementations
 * cannot drift silently. UI/DOM code lives at the bottom, guarded so the
 * logic half also loads in node.
 */
(function () {
  'use strict';

  // A payer covering more than this many players is registration staff
  // processing entries, not a parent booking a room (same as the CLI).
  const BULK_PAYER_THRESHOLD = 3;

  const EXPORT_REQUIRED_COLUMNS = ['LastName', 'FirstName', 'PayerName'];

  // ── Name normalization (ports of the hotel_audit.py helpers) ──────────

  function cleanName(s) {
    // Strip parenthesized annotations ((GM), (Withdrawn)) and tidy spaces.
    return String(s || '').replace(/\([^)]*\)/g, '').split(/\s+/).filter(Boolean).join(' ');
  }

  function titleCase(s) {
    // Python str.title(): each alphabetic run capitalized (handles
    // hyphens, apostrophes, and accented letters as run boundaries).
    return s.replace(/\p{L}+/gu, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase());
  }

  function smartCase(s) {
    // ALL CAPS or all-lower -> Title Case; mixed case (McDonald) untouched.
    s = String(s || '').trim();
    if (!/\p{L}/u.test(s)) return s;
    if (s === s.toUpperCase() || s === s.toLowerCase()) return titleCase(s);
    return s;
  }

  function nameKey(last, first) {
    // Identity key: (last name, FIRST TOKEN of first name), case-folded.
    // First-token matching absorbs middle names ("Brightwater, Ana Marie" on
    // the entry list is "Brightwater, Ana" in the export).
    const l = cleanName(last).toLowerCase().split(/\s+/).filter(Boolean).join(' ');
    const tokens = cleanName(first).toLowerCase().split(/\s+/).filter(Boolean);
    return l + ' ' + (tokens.length ? tokens[0] : '');
  }

  function splitLastFirst(name) {
    // Split a "Last, First M" string; falls back for comma-less input.
    name = cleanName(name);
    const comma = name.indexOf(',');
    if (comma !== -1) {
      return [name.slice(0, comma).trim(), name.slice(comma + 1).trim()];
    }
    const parts = name.split(/\s+/).filter(Boolean);
    if (parts.length > 1) {
      return [parts[parts.length - 1], parts.slice(0, -1).join(' ')];
    }
    return [name, ''];
  }

  function padZip(z) {
    // Restore leading zeros Excel strips (2155 -> 02155). ZIP+4 untouched.
    z = String(z || '').trim();
    if (/^\d{1,4}$/.test(z)) return z.padStart(5, '0');
    return z;
  }

  // ── Entry-list parsing (browser only: needs DOMParser) ────────────────

  function parseEntryListHtml(html) {
    // Same structure contract as hotel_audit.parse_entry_list: the player
    // table has a header row class="success"; player rows have >=8 <td>;
    // the first cell carries clean "Last, First M" in data-order and may
    // append "(GM)"/"(Withdrawn)" in its visible text.
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const tables = Array.from(doc.querySelectorAll('table'));
    if (!tables.length) return [];

    let playerTable = tables.find((t) => t.querySelector('tr.success'));
    if (!playerTable) {
      playerTable = tables.reduce((a, b) =>
        b.querySelectorAll('tr').length > a.querySelectorAll('tr').length ? b : a);
    }

    const players = [];
    for (const row of playerTable.querySelectorAll('tr')) {
      if (row.classList.contains('success')) continue; // header row
      const cols = row.querySelectorAll('td');
      if (cols.length < 8) continue;
      const cellText = cols[0].textContent.trim();
      const rawName = cols[0].getAttribute('data-order') || cellText;
      const name = cleanName(rawName);
      const lower = name.toLowerCase();
      if (!name || lower.startsWith('player') || lower.startsWith('name') ||
          lower.startsWith('filter')) continue;
      const lf = splitLastFirst(name);
      players.push({
        last: lf[0],
        first: lf[1],
        uscf_id: cols[4].textContent.trim() || null,
        state: cols[6].textContent.trim() || '',
        section: cols[7].textContent.trim() || '',
        withdrawn: cellText.toLowerCase().includes('(withdrawn)'),
      });
    }
    return players;
  }

  function dedupScraped(players) {
    // USCF ID is the identity where present; name key otherwise. First
    // sighting wins; a withdrawn duplicate never un-withdraws an active row.
    const seen = new Map();
    for (const p of players) {
      const key = p.uscf_id ? 'id:' + p.uscf_id : 'name:' + nameKey(p.last, p.first);
      const existing = seen.get(key);
      if (!existing) seen.set(key, p);
      else if (existing.withdrawn && !p.withdrawn) seen.set(key, p);
    }
    return Array.from(seen.values());
  }

  // ── Registration export parsing ────────────────────────────────────────

  function parseCsv(text) {
    // RFC 4180: quoted fields, "" escapes, CRLF/CR/LF rows. Strips a BOM.
    if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
    const rows = [];
    let field = '', row = [], inQuotes = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inQuotes) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; }
          else inQuotes = false;
        } else field += c;
      } else if (c === '"') {
        inQuotes = true;
      } else if (c === ',') {
        row.push(field); field = '';
      } else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(field); field = '';
        rows.push(row); row = [];
      } else field += c;
    }
    if (field.length || row.length) { row.push(field); rows.push(row); }
    return rows.filter((r) => r.length > 1 || (r[0] || '').trim() !== '');
  }

  function rowsToObjects(rows) {
    // First row is the header. Validates the required export columns and
    // fails loud (same contract as hotel_audit.load_export).
    if (!rows.length) throw new Error('The file is empty.');
    const header = rows[0].map((h) => String(h || '').trim());
    const missing = EXPORT_REQUIRED_COLUMNS.filter((c) => !header.includes(c));
    if (missing.length) {
      throw new Error(
        'The export is missing required column(s): ' + missing.join(', ') +
        '. Found: ' + header.join(', ') +
        '. Expected: LastName, FirstName, City, State, ZipCode, PayerName.');
    }
    return rows.slice(1).map((r) => {
      const obj = {};
      header.forEach((h, i) => { obj[h] = r[i] !== undefined ? String(r[i]) : ''; });
      return obj;
    });
  }

  // ── Merge (exact port of hotel_audit.build_people) ────────────────────

  function newPerson(last, first, type, source) {
    return {
      last: smartCase(last), first: smartCase(first),
      city: '', state: '', zip: '',
      type: type, source: source, section: '',
      withdrawn: false, paid_for: [], flags: [],
    };
  }

  function addFlag(person, msg) {
    if (!person.flags.includes(msg)) person.flags.push(msg);
  }

  function applyAddress(person, row) {
    // The export is the address authority: the folio shows the guest's
    // HOME address; the entry list's State is the USCF federation state.
    const city = String(row.City || '').trim();
    const state = String(row.State || '').trim();
    const zip = String(row.ZipCode || '').trim();
    if (city) person.city = smartCase(city);
    if (state) person.state = state.toUpperCase();
    if (zip) person.zip = padZip(zip);
    if (city.includes(',')) {
      addFlag(person, 'check city field (looks like a full address)');
    }
  }

  function buildPeople(scraped, exportRows) {
    const stats = {
      scraped_players: 0, scraped_withdrawn: 0, export_rows: 0,
      matched_both: 0, scrape_only: 0, export_only: 0,
      payers_added: 0, payers_already_players: 0, bulk_payers: 0,
      final_people: 0,
    };
    const people = [];

    // A. entry-list players; distinct USCF IDs under one name key are
    //    genuinely different people and keep separate rows.
    const scrapeGroups = new Map();
    for (const p of scraped) {
      stats.scraped_players += 1;
      if (p.withdrawn) stats.scraped_withdrawn += 1;
      const person = newPerson(p.last, p.first, 'Player', 'entry list');
      person.state = String(p.state || '').toUpperCase();
      person.section = p.section || '';
      person.withdrawn = !!p.withdrawn;
      const nkey = nameKey(p.last, p.first);
      if (!scrapeGroups.has(nkey)) scrapeGroups.set(nkey, []);
      scrapeGroups.get(nkey).push(person);
      people.push(person);
    }
    for (const group of scrapeGroups.values()) {
      if (group.length > 1) {
        for (const person of group) {
          addFlag(person, 'shares a name with another entry ' +
                          '(distinct USCF IDs); verify identity');
        }
      }
    }

    // B. export rows: dedup players by name key, splitting on conflicting
    //    in-export states; collect payers.
    const exportGroups = new Map();  // nkey -> Map(state_lower -> {names,row})
    const payerOf = new Map();       // payer nkey -> {last,first,players:Set,row}
    for (const r of exportRows) {
      stats.export_rows += 1;
      const last = String(r.LastName || '').trim();
      const first = String(r.FirstName || '').trim();
      const nkey = nameKey(last, first);
      if (!exportGroups.has(nkey)) exportGroups.set(nkey, new Map());
      const variants = exportGroups.get(nkey);
      let stateL = String(r.State || '').trim().toLowerCase();
      // a stateless row folds into any existing variant; a stated row
      // claims the stateless variant if that is all that exists
      if (variants.has(stateL)) {
        /* existing variant: nothing to add */
      } else if (!stateL && variants.size) {
        stateL = variants.keys().next().value;
      } else if (stateL && variants.size === 1 && variants.has('')) {
        variants.set(stateL, variants.get(''));
        variants.delete('');
      }
      if (!variants.has(stateL)) {
        variants.set(stateL, { names: { last: last, first: first }, row: r });
      }

      const payer = String(r.PayerName || '').trim();
      if (payer) {
        const pl = splitLastFirst(payer);
        const pkey = nameKey(pl[0], pl[1]);
        if (pkey !== nkey) {
          if (!payerOf.has(pkey)) {
            payerOf.set(pkey, { last: pl[0], first: pl[1], players: new Set(), row: r });
          }
          payerOf.get(pkey).players.add((first + ' ' + last).trim());
        }
      }
    }

    // C. join: export enriches matched scrape rows; unmatched export
    //    variants become their own people (side events etc.).
    for (const [nkey, variants] of exportGroups) {
      const multiState = variants.size > 1;
      const matched = scrapeGroups.get(nkey);
      for (const [stateL, entry] of variants) {
        let target = null;
        if (matched) {
          target = matched.find((p) => p.state.toLowerCase() === stateL) || null;
          if (!target && !multiState) target = matched[0];
        }
        if (target) {
          stats.matched_both += 1;
          target.source = 'entry list+export';
        } else {
          target = newPerson(entry.names.last, entry.names.first, 'Player', 'export');
          stats.export_only += 1;
          people.push(target);
        }
        applyAddress(target, entry.row);
        if (!entry.names.last || !entry.names.first) {
          addFlag(target, 'blank name in source data');
        }
        if (multiState) {
          addFlag(target, 'same name in multiple states; possibly distinct people');
        }
      }
    }

    if (exportRows.length) {
      for (const [nkey, group] of scrapeGroups) {
        if (!exportGroups.has(nkey)) stats.scrape_only += group.length;
      }
    }

    // D. external payers (likely booked the room under their own name).
    for (const [pkey, entry] of payerOf) {
      if (scrapeGroups.has(pkey) || exportGroups.has(pkey)) {
        stats.payers_already_players += 1;
        continue;
      }
      stats.payers_added += 1;
      const person = newPerson(entry.last, entry.first, 'Payer', 'export');
      // a parent shares the player's home address: the folio match hook
      applyAddress(person, entry.row);
      const n = entry.players.size;
      if (n > BULK_PAYER_THRESHOLD) {
        stats.bulk_payers += 1;
        addFlag(person, 'bulk payer, paid ' + n + ' entries (likely registration staff)');
      } else {
        person.paid_for = Array.from(entry.players).sort();
      }
      people.push(person);
    }

    stats.final_people = people.length;
    return { people: people, stats: stats };
  }

  // ── Executive summary ──────────────────────────────────────────────────

  function buildSummary(stats, meta) {
    // Rows of [label, value] used both on the page and the Summary sheet.
    const lines = [];
    lines.push(['Event', meta.eventLabel || 'none (export only)']);
    lines.push(['Generated', meta.generated]);
    if (meta.entryCode) lines.push(['Entry list', meta.entryCode]);
    if (stats.scraped_players) {
      lines.push(['Entry-list players (unique)', stats.scraped_players]);
      lines.push(['  of which withdrawn', stats.scraped_withdrawn]);
    }
    if (stats.export_rows) {
      lines.push(['Export rows', stats.export_rows]);
      const uniqueExport = stats.matched_both + stats.export_only;
      lines.push(['  unique people in export', uniqueExport]);
      lines.push(['  duplicate rows removed', stats.export_rows - uniqueExport]);
    }
    if (stats.scraped_players && stats.export_rows) {
      lines.push(['Matched in both sources', stats.matched_both]);
      lines.push(['Entry list only', stats.scrape_only]);
      lines.push(['Export only (side events)', stats.export_only]);
    }
    if (stats.export_rows) {
      lines.push(['Payers added (paid for someone else)', stats.payers_added]);
      lines.push(['  of which bulk/staff', stats.bulk_payers]);
      lines.push(['Payers already on the list as players', stats.payers_already_players]);
    }
    lines.push(['Final audit list', stats.final_people + ' people']);
    return lines;
  }

  // ── Workbook (ExcelJS; same sheets/styling as the CLI + Summary) ──────

  function sortedPeople(people) {
    return people.slice().sort(function (a, b) {
      const al = a.last.toLowerCase(), bl = b.last.toLowerCase();
      if (al !== bl) return al < bl ? -1 : 1;
      const af = a.first.toLowerCase(), bf = b.first.toLowerCase();
      if (af !== bf) return af < bf ? -1 : 1;
      return 0;
    });
  }

  function buildWorkbook(ExcelJSRef, people, stats, meta) {
    const wb = new ExcelJSRef.Workbook();
    const ordered = sortedPeople(people);

    const hdrStyle = {
      font: { bold: true, color: { argb: 'FFFFFFFF' } },
      fill: { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF1F4E78' } },
      alignment: { vertical: 'middle' },
    };

    function styleHeader(ws, nCols) {
      const row = ws.getRow(1);
      for (let c = 1; c <= nCols; c++) {
        const cell = row.getCell(c);
        cell.font = hdrStyle.font;
        cell.fill = hdrStyle.fill;
        cell.alignment = hdrStyle.alignment;
      }
      ws.views = [{ state: 'frozen', ySplit: 1 }];
    }

    const audit = wb.addWorksheet('Audit List');
    audit.columns = [
      { header: 'LastName', width: 18 }, { header: 'FirstName', width: 18 },
      { header: 'City', width: 22 }, { header: 'State', width: 7 },
      { header: 'Zip', width: 11 },
    ];
    for (const p of ordered) {
      audit.addRow([p.last, p.first, p.city, p.state, p.zip]);
    }
    styleHeader(audit, 5);
    audit.autoFilter = 'A1:E' + audit.rowCount;

    const ref = wb.addWorksheet('Reference');
    ref.columns = [
      { header: 'LastName', width: 18 }, { header: 'FirstName', width: 18 },
      { header: 'Type', width: 8 }, { header: 'Source', width: 18 },
      { header: 'Section', width: 14 }, { header: 'Notes', width: 40 },
      { header: 'Flags', width: 44 },
    ];
    for (const p of ordered) {
      const notes = p.paid_for.length ? 'Paid for: ' + p.paid_for.join(', ') : '';
      const flags = p.flags.slice();
      if (p.withdrawn) flags.unshift('withdrawn from event; may still have booked');
      ref.addRow([p.last, p.first, p.type, p.source, p.section, notes, flags.join('; ')]);
    }
    styleHeader(ref, 7);
    ref.autoFilter = 'A1:G' + ref.rowCount;

    const summary = wb.addWorksheet('Summary');
    summary.columns = [{ header: 'Item', width: 40 }, { header: 'Value', width: 24 }];
    for (const line of buildSummary(stats, meta)) summary.addRow(line);
    styleHeader(summary, 2);

    return wb;
  }

  // ── Node export for the pytest parity gate (no DOM below this used) ───

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      cleanName, smartCase, nameKey, splitLastFirst, padZip,
      dedupScraped, parseCsv, rowsToObjects, buildPeople, buildSummary,
      sortedPeople, parseEntryListHtml, buildWorkbook,
    };
    return; // node: skip the browser UI half
  }

  // ── Browser UI ─────────────────────────────────────────────────────────

  const AUDIT_ENDPOINT = (function () {
    const h = (typeof location !== 'undefined') ? location.hostname : '';
    if (h === 'localhost' || h === '127.0.0.1' || h === '') {
      return 'http://localhost:8787/cca-entrylist';
    }
    return 'https://chess-ask.hater-andrewd.workers.dev/cca-entrylist';
  })();

  const AUDIT_FETCH_TIMEOUT_MS = 60000;

  let auditInited = false;
  let auditInFlight = false;
  let auditDownload = null; // { blob, filename }

  function auditEl(id) { return document.getElementById(id); }

  function showAuditBanner(kind, msg) {
    const b = auditEl('auditBanner');
    if (!b) return;
    b.className = 'audit-banner ' + kind;
    b.textContent = msg;
    b.hidden = false;
  }

  function hideAuditBanner() {
    const b = auditEl('auditBanner');
    if (b) b.hidden = true;
  }

  function populateAuditEvents() {
    const sel = auditEl('auditEvent');
    if (!sel || typeof TOURNAMENT_DATA === 'undefined') return;
    const events = (TOURNAMENT_DATA.tournaments || []).slice()
      .sort(function (a, b) {
        return String(b.event_start || '').localeCompare(String(a.event_start || ''));
      });
    sel.innerHTML = '';
    const none = document.createElement('option');
    none.value = '';
    none.textContent = 'No event (clean the export only)';
    sel.appendChild(none);
    for (const t of events) {
      const opt = document.createElement('option');
      opt.value = t.family + '|' + t.year;
      opt.textContent = t.family + ' ' + t.year;
      sel.appendChild(opt);
    }
  }

  async function readUploadedFile(file) {
    // Returns export row objects from a .csv or .xlsx upload.
    const name = (file.name || '').toLowerCase();
    if (name.endsWith('.xlsx') || name.endsWith('.xls')) {
      if (typeof ExcelJS === 'undefined') {
        throw new Error('The spreadsheet library failed to load; reload the page and try again.');
      }
      const wb = new ExcelJS.Workbook();
      await wb.xlsx.load(await file.arrayBuffer());
      const ws = wb.worksheets[0];
      if (!ws) throw new Error('The workbook has no sheets.');
      const rows = [];
      ws.eachRow(function (row) {
        const vals = [];
        for (let c = 1; c <= row.cellCount; c++) vals.push(row.getCell(c).text || '');
        rows.push(vals);
      });
      return rowsToObjects(rows);
    }
    return rowsToObjects(parseCsv(await file.text()));
  }

  async function fetchEntryList(family, year) {
    const controller = new AbortController();
    const timer = setTimeout(function () { controller.abort(); }, AUDIT_FETCH_TIMEOUT_MS);
    try {
      const resp = await fetch(
        AUDIT_ENDPOINT + '?event=' + encodeURIComponent(family) + '&year=' + encodeURIComponent(year),
        { signal: controller.signal });
      if (!resp.ok) {
        let detail = '';
        try { detail = (await resp.json()).message || ''; } catch (e) { /* html body */ }
        throw new Error('Entry list fetch failed (HTTP ' + resp.status + ')' +
                        (detail ? ': ' + detail : '') +
                        '. The page may not be published yet.');
      }
      return { html: await resp.text(), code: resp.headers.get('X-Entry-Code') || '' };
    } finally {
      clearTimeout(timer);
    }
  }

  function renderSummary(lines) {
    const box = auditEl('auditSummary');
    if (!box) return;
    box.innerHTML = '';
    const table = document.createElement('table');
    table.className = 'audit-summary-table';
    for (const line of lines) {
      const tr = document.createElement('tr');
      const th = document.createElement('th');
      th.textContent = line[0];
      const td = document.createElement('td');
      td.textContent = String(line[1]);
      tr.appendChild(th); tr.appendChild(td);
      table.appendChild(tr);
    }
    box.appendChild(table);
    box.hidden = false;
  }

  async function runAudit() {
    if (auditInFlight) return;
    const sel = auditEl('auditEvent');
    const fileInput = auditEl('auditFile');
    const btn = auditEl('auditGenerate');
    const dl = auditEl('auditDownload');
    const eventVal = sel ? sel.value : '';
    const file = fileInput && fileInput.files.length ? fileInput.files[0] : null;

    hideAuditBanner();
    auditEl('auditSummary').hidden = true;
    dl.hidden = true;
    auditDownload = null;

    if (!eventVal && !file) {
      showAuditBanner('error', 'Pick an event, upload the registration export, or both.');
      return;
    }

    auditInFlight = true;
    btn.disabled = true;
    btn.textContent = 'Working…';

    try {
      let scraped = [];
      let entryCode = '';
      let eventLabel = '';
      if (eventVal) {
        const parts = eventVal.split('|');
        const family = parts[0], year = parts[1];
        eventLabel = family + ' ' + year;
        showAuditBanner('info', 'Fetching the entry list for ' + eventLabel + '…');
        const fetched = await fetchEntryList(family, year);
        scraped = dedupScraped(parseEntryListHtml(fetched.html));
        entryCode = fetched.code;
        if (!scraped.length) {
          throw new Error('No players found on the entry list for ' + eventLabel +
                          '. The list may be empty or the page layout changed.');
        }
      }

      let exportRows = [];
      if (file) {
        showAuditBanner('info', 'Reading ' + file.name + '…');
        exportRows = await readUploadedFile(file);
      }

      const result = buildPeople(scraped, exportRows);
      const meta = {
        eventLabel: eventLabel,
        entryCode: entryCode,
        generated: new Date().toISOString().slice(0, 10),
      };
      const lines = buildSummary(result.stats, meta);

      if (typeof ExcelJS === 'undefined') {
        throw new Error('The spreadsheet library failed to load; reload the page and try again.');
      }
      const wb = buildWorkbook(ExcelJS, result.people, result.stats, meta);
      const buffer = await wb.xlsx.writeBuffer();
      const blob = new Blob([buffer], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      const stem = entryCode || (file ? file.name.replace(/\.[^.]*$/, '') : 'export');
      auditDownload = { blob: blob, filename: 'hotel_audit_' + stem + '.xlsx' };

      renderSummary(lines);
      dl.hidden = false;
      showAuditBanner('ok', 'Done: ' + result.stats.final_people +
                      ' people on the audit list. Download below.');
    } catch (e) {
      showAuditBanner('error', e && e.message ? e.message : String(e));
    } finally {
      auditInFlight = false;
      btn.disabled = false;
      btn.textContent = 'Generate audit list';
    }
  }

  function downloadAudit() {
    if (!auditDownload) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(auditDownload.blob);
    a.download = auditDownload.filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 10000);
  }

  function initAuditTab() {
    if (auditInited) return;
    auditInited = true;
    populateAuditEvents();
    auditEl('auditGenerate').addEventListener('click', runAudit);
    auditEl('auditDownload').addEventListener('click', downloadAudit);
  }

  window.initAuditTab = initAuditTab;
})();
