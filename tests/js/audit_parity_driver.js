// Node driver for tests/test_audit_js_parity.py.
//
// Reads a JSON payload from stdin:
//   { scraped: [...], export_rows: [...], csv_text: "...", helper_cases: {...} }
// loads docs/audit.js (its module.exports guard skips the browser UI half),
// and prints JSON with the JS-side results for the pytest to compare against
// the Python implementation.

const path = require('path');
const audit = require(path.join(__dirname, '..', '..', 'docs', 'audit.js'));

let input = '';
process.stdin.on('data', (d) => { input += d; });
process.stdin.on('end', () => {
  const payload = JSON.parse(input);

  const result = audit.buildPeople(payload.scraped || [], payload.export_rows || []);

  let csvRows = null;
  if (typeof payload.csv_text === 'string') {
    csvRows = audit.rowsToObjects(audit.parseCsv(payload.csv_text));
  }

  const helpers = {};
  const cases = payload.helper_cases || {};
  if (cases.smart_case) helpers.smart_case = cases.smart_case.map(audit.smartCase);
  if (cases.pad_zip) helpers.pad_zip = cases.pad_zip.map(audit.padZip);
  if (cases.name_key) {
    helpers.name_key = cases.name_key.map((c) => audit.nameKey(c[0], c[1]));
  }
  if (cases.split_last_first) {
    helpers.split_last_first = cases.split_last_first.map(audit.splitLastFirst);
  }
  if (cases.dedup_scraped) {
    helpers.dedup_scraped = audit.dedupScraped(cases.dedup_scraped);
  }

  process.stdout.write(JSON.stringify({
    people: result.people,
    stats: result.stats,
    csv_rows: csvRows,
    helpers: helpers,
  }));
});
