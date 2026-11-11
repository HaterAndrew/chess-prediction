import type { ReceiptCard } from "./types";
export type RegistrationCard = Pick<ReceiptCard, "family" | "year" | "status" | "event_start" | "event_end">;

// Source rows exist only during collection. Storage/RPC uses this closed aggregate shape.
export interface RegistrationAggregate {
  version: 1;
  family: string;
  year: number;
  tournament_id: string;
  source_as_of: string;
  active: number;
  withdrawn: number;
  total: number;
  ts_count: number;
  first_reg: string | null;
  last_reg: string | null;
  daily: Array<{ T: number; daily_regs: number }>;
  calendar_daily: Array<{ date: string; daily_regs: number }>;
}
interface RegistrationSource {
  request(path: string, fields: Record<string, string>, method: string): Promise<string>;
}
const DAY = 86_400_000;
const LIMIT = 10_000;
const timestamp = /^20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/;
function millis(value: string): number {
  const parsed = Date.parse(value.replace(" ", "T") + "Z");
  if (!timestamp.test(value) || !Number.isFinite(parsed)
      || new Date(parsed).toISOString().slice(0, 19).replace("T", " ") !== value) throw new Error("registration_time_invalid");
  return parsed;
}

// This local display is the export's registered_time (490/490 unique-name
// historical controls match exactly; all 492 timestamp/curve bins match).
// created_at is a different database time. The source GMT label disagrees
// with its UTC title by one hour on 13 historical rows; do not reconvert the
// export-equivalent local display using that label.
export function registrationTime(value: unknown): string | null {
  if (value === null || value === "") return null;
  if (typeof value !== "string") throw new Error("registration_time_invalid");
  const match = /^<span title="(20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC">(20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})<br \/>\(GMT([+-])(\d{2}):(\d{2})\)<\/span>$/.exec(value);
  if (!match || Number(match[4]) > 14 || Number(match[5]) > 59 || Number(match[4]) === 14 && Number(match[5]) !== 0) throw new Error("registration_time_invalid");
  millis(match[1]);
  millis(match[2]);
  return match[2];
}
function count(value: unknown): number {
  const n = typeof value === "string" && /^(0|[1-9]\d*)$/.test(value) ? Number(value) : value;
  if (typeof n !== "number" || !Number.isSafeInteger(n) || n < 0 || n > LIMIT) throw new Error("registration_schema_changed");
  return n;
}
function page(text: string, maximum: number) {
  let value;
  try { value = JSON.parse(text); } catch { throw new Error("registration_schema_changed"); }
  if (!value || typeof value !== "object" || !Array.isArray(value.aaData) || value.aaData.length > maximum
      || value.aaData.some((r: unknown) => !r || typeof r !== "object" || Array.isArray(r))) throw new Error("registration_schema_changed");
  const total = count(value.iTotalDisplayRecords);
  if (count(value.iTotalRecords) !== total) throw new Error("registration_schema_changed");
  return { total, rows: value.aaData as Record<string, unknown>[] };
}
function filters(id: string, status: string, start: number, length: number) {
  return { tournment: id, status, reg_filter: "all", sec_filter: "all", filterBy: "all", sortBy: "created_at", sortOrder: "ASC",
    nameformat: "1", advance_search: "all", searchBy: "", registration_before: "", show: "all", draw: "1", start: String(start), length: String(length) };
}

export async function acquireRegistrations(client: RegistrationSource, card: { family: string; year: number }, id: string,
  sourceAsOf: string, onIdentity?: (id: string, row: Record<string, unknown>) => void): Promise<RegistrationAggregate> {
  if (!/^\d{1,12}$/.test(id) || !Number.isFinite(Date.parse(sourceAsOf))) throw new Error("registration_schema_changed");
  const totals: number[] = [];
  const identities = new Set<string>();
  const times: string[] = [];
  let bytes = 0;
  for (const status of ["active", "withdrawn"]) {
    let total: number | null = null;
    let received = 0;
    for (let start = 0; start < LIMIT; start += 1000) {
      const text = await client.request("ajaxRegistrationDataTable.php", filters(id, status, start, 1000), "POST");
      bytes += new TextEncoder().encode(text).byteLength;
      if (bytes > 8_000_000) throw new Error("source_too_many_rows");
      const result = page(text, 1000);
      if (total !== null && total !== result.total) throw new Error("source_changed_during_read");
      total = result.total;
      for (const row of result.rows) {
        const key = String(row.eventId ?? "");
        if (String(row.tourid) !== id || !/^\d{1,20}$/.test(key) || identities.has(key)) throw new Error("registration_identity_invalid");
        identities.add(key);
        // Request-local observers do not change the closed aggregate output.
        onIdentity?.(key, row);
        const time = registrationTime(row.createdAt);
        if (time !== null) {
          // Display times have explicit source offsets validated above. Permit
          // the maximum local offset, without guessing the operator timezone.
          if (millis(time) > Date.parse(sourceAsOf) + 14 * 3_600_000) throw new Error("registration_time_invalid");
          times.push(time);
        }
      }
      received += result.rows.length;
      if (received === total) break;
      if (result.rows.length !== 1000 || received > total) throw new Error("source_incomplete");
    }
    if (received !== total) throw new Error("source_incomplete");
    totals.push(total);
  }
  if (identities.size > LIMIT) throw new Error("source_too_many_rows");
  for (const [i, status] of ["active", "withdrawn"].entries()) {
    const fence = page(await client.request("ajaxRegistrationDataTable.php", filters(id, status, 0, 1), "POST"), 1);
    if (fence.total !== totals[i]) throw new Error("source_changed_during_read");
  }
  if (identities.size > 0 && times.length === 0) throw new Error("registration_timestamps_missing");
  times.sort();
  const first = times[0] ?? null, last = times.at(-1) ?? null;
  const bins = new Map<number, number>(), dates = new Map<string, number>();
  for (const time of times) {
    const T = Math.floor((millis(last!) - millis(time)) / DAY);
    bins.set(T, (bins.get(T) ?? 0) + 1);
    const date = time.slice(0, 10);
    dates.set(date, (dates.get(date) ?? 0) + 1);
  }
  return { version: 1, family: card.family, year: card.year, tournament_id: id, source_as_of: sourceAsOf,
    active: totals[0], withdrawn: totals[1], total: identities.size, ts_count: times.length, first_reg: first, last_reg: last,
    daily: [...bins].sort((a, b) => b[0] - a[0]).map(([T, daily_regs]) => ({ T, daily_regs })),
    calendar_daily: [...dates].sort(([a], [b]) => a.localeCompare(b)).map(([date, daily_regs]) => ({ date, daily_regs })) };
}

const FIELDS = ["version", "family", "year", "tournament_id", "source_as_of", "active", "withdrawn", "total", "ts_count", "first_reg", "last_reg", "daily", "calendar_daily"];
export function validateRegistrations(raw: unknown, card: { family: string; year: number }): RegistrationAggregate {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error("registration_cache_invalid");
  const x = raw as RegistrationAggregate;
  const integer = (n: number) => Number.isSafeInteger(n) && n >= 0 && n <= LIMIT;
  if (Object.keys(x).sort().join() !== [...FIELDS].sort().join() || x.version !== 1 || x.family !== card.family || x.year !== card.year
      || !/^\d{1,12}$/.test(x.tournament_id) || !/^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(x.source_as_of)
      || !Number.isFinite(Date.parse(x.source_as_of)) || new Date(x.source_as_of).toISOString() !== x.source_as_of || ![x.active, x.withdrawn, x.total, x.ts_count].every(integer)
      || x.active + x.withdrawn !== x.total || x.ts_count > x.total || !Array.isArray(x.daily) || !Array.isArray(x.calendar_daily)
      || x.daily.length > 2000 || x.calendar_daily.length > 2000) throw new Error("registration_cache_invalid");
  if (x.ts_count === 0) {
    if (x.total !== 0 || x.first_reg !== null || x.last_reg !== null || x.daily.length || x.calendar_daily.length) throw new Error("registration_cache_invalid");
    return x;
  }
  if (typeof x.first_reg !== "string" || typeof x.last_reg !== "string" || millis(x.first_reg) > millis(x.last_reg)
      || millis(x.last_reg) > Date.parse(x.source_as_of) + 14 * 3_600_000) throw new Error("registration_cache_invalid");
  let previous = Infinity, sum = 0;
  for (const bin of x.daily) {
    if (!bin || Object.keys(bin).sort().join() !== "T,daily_regs" || !integer(bin.T) || bin.T >= previous
        || !integer(bin.daily_regs) || !bin.daily_regs) throw new Error("registration_cache_invalid");
    previous = bin.T; sum += bin.daily_regs;
  }
  if (sum !== x.ts_count || previous !== 0 || x.daily[0]?.T !== Math.floor((millis(x.last_reg) - millis(x.first_reg)) / DAY)) throw new Error("registration_cache_invalid");
  let prior = ""; sum = 0;
  for (const bin of x.calendar_daily) {
    if (!bin || Object.keys(bin).sort().join() !== "daily_regs,date" || typeof bin.date !== "string" || bin.date.length !== 10
        || bin.date <= prior || !integer(bin.daily_regs) || !bin.daily_regs) throw new Error("registration_cache_invalid");
    millis(bin.date + " 00:00:00"); prior = bin.date; sum += bin.daily_regs;
  }
  if (sum !== x.ts_count || x.calendar_daily[0]?.date !== x.first_reg.slice(0, 10)
      || prior !== x.last_reg.slice(0, 10)) throw new Error("registration_cache_invalid");
  return x;
}
