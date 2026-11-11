// Join by unique federation IDs, or an exact unique name digest for unrated
// players. Name digests are request-local; only public registration IDs persist.
import { sha256 } from "./types";
const absentUscf = (value: string) => ["", "new"].includes(value.trim().toLowerCase());
const absentFide = (value: string) => value.trim() === "";
const normalizedName = (name: string) => name.normalize("NFKC").replace(/\s+/g, " ").trim().toLowerCase();
export interface PublicRegistration { id: string; uscf: string; fide: string; name_hash?: string; new_uscf?: true }

export async function parsePublicRegistrations(html: string): Promise<PublicRegistration[]> {
  interface Cell { tag: string; text: string }
  interface Layout { expectedCells: number }
  interface Row { id: string | null; cells: Cell[]; cell: Cell | null; layout?: Layout }
  const tables: Layout[] = [];
  const stack: Row[] = [];
  const rows: Array<PublicRegistration & { name: string; unrated: boolean }> = [];
  let headerVerified = false;
  const expected = ["player's name", "player's name", "fide id", "fide rating", "uscf id", "uscf rating", "state", "section", "schedule", "bye(s)"];
  const scholastic = [...expected.slice(0, 8), "team code", "school", "grade", "bye(s)"];
  const clean = (v: string) => v.replace(/\s+/g, " ").trim().toLowerCase();
  const rewriter = new HTMLRewriter().on("table", {
    element(el) {
      const layout: Layout = { expectedCells: 0 };
      tables.push(layout);
      el.onEndTag(() => { if (tables.pop() !== layout) throw new Error("public_registration_schema_changed"); });
    },
  }).on("tr", {
    element(el) {
      const row: Row = { id: null, cells: [], cell: null, layout: tables.at(-1) };
      stack.push(row);
      el.onEndTag(() => {
        if (stack.pop() !== row) throw new Error("public_registration_schema_changed");
        const headers = row.cells.filter(c => c.tag === "th").map(c => clean(c.text));
        const layout = [expected, scholastic].find(candidate => headers.length === candidate.length && headers.every((v, i) => v === candidate[i]));
        if (headers.length && row.layout) row.layout.expectedCells = layout?.length ?? 0;
        if (layout) headerVerified = true;
        if (!row.id) return;
        const cells = row.cells.filter(c => c.tag === "td");
        if (!row.layout?.expectedCells || cells.length !== row.layout.expectedCells) throw new Error("public_registration_schema_changed");
        const uscf = clean(cells[4].text);
        const fide = /^\s*([1-9]\d{2,11})\b/.exec(cells[2].text)?.[1] ?? "";
        const validUscf = /^[1-9]\d{7}$/.test(uscf) ? uscf : "";
        rows.push({ id: row.id, uscf: validUscf, fide, name: normalizedName(cells[1].text),
          unrated: absentUscf(uscf) && absentFide(cells[2].text),
          ...(uscf === "new" && absentFide(cells[2].text) ? { new_uscf: true as const } : {}) });
      });
    },
  }).on("td, th", {
    element(el) {
      const row = stack.at(-1);
      if (!row) return;
      const cell = { tag: el.tagName, text: "" };
      row.cells.push(cell); row.cell = cell;
      el.onEndTag(() => { if (row.cell === cell) row.cell = null; });
    },
    text(chunk) { const cell = stack.at(-1)?.cell; if (cell) cell.text += chunk.text; },
  }).on("span[id]", {
    element(el) {
      const id = /^#bname_(\d+)$/.exec(el.getAttribute("id") ?? "")?.[1];
      const row = stack.at(-1);
      if (!id || !row) return;
      if (row.id && row.id !== id) throw new Error("public_registration_schema_changed");
      row.id = id;
    },
  });
  await rewriter.transform(new Response(html)).text();
  if (!headerVerified || new Set(rows.map(r => r.id)).size !== rows.length) throw new Error("public_registration_schema_changed");
  // A rated namesake also makes an unrated name ambiguous. Keep all names
  // request-local, and expose a digest only for an explicit, unique NEW row.
  const names = new Map<string, number>();
  for (const row of rows) names.set(row.name, (names.get(row.name) ?? 0) + 1);
  return Promise.all(rows.map(async ({ name, unrated, ...row }) => ({ ...row,
    ...(unrated && name && names.get(name) === 1 ? { name_hash: await sha256(name) } : {}) })));
}

/** Every source row must map uniquely. The model's cohort hash then proves the set. */
export async function matchPublicRegistrations(source: Record<string, unknown>[], publicRows: PublicRegistration[]): Promise<string[] | null> {
  if (source.length > publicRows.length) return null;
  const selected: string[] = [];
  for (const row of source) {
    const uscf = String(row.uscf_id ?? "").trim();
    const fide = String(row.fide_id ?? "").trim();
    const first = typeof row.player_first_name === "string" ? row.player_first_name.trim() : "";
    const last = typeof row.player_last_name === "string" ? row.player_last_name.trim() : "";
    const validUscf = /^[1-9]\d{7}$/.test(uscf);
    const validFide = /^[1-9]\d{2,11}$/.test(fide);
    const nameHash = typeof row.uscf_id === "string" && typeof row.fide_id === "string"
      && (absentUscf(uscf) || validUscf) && (absentFide(fide) || validFide) && first && last
      ? await sha256(normalizedName(`${first} ${last}`)) : null;
    let candidates = validUscf ? publicRows.filter(p => p.uscf === uscf)
      : validFide ? publicRows.filter(p => p.fide === fide) : [];
    // The private report may already contain an assigned membership ID while
    // the generated public list still says NEW. No conflicting public ID may
    // be bypassed, and the public parser has proved this name globally unique.
    if (!candidates.length && nameHash
        && !publicRows.some(p => validUscf && p.uscf === uscf || validFide && p.fide === fide)) {
      candidates = publicRows.filter(p => !p.uscf && !p.fide && p.name_hash === nameHash
        && (!validUscf && !validFide || p.new_uscf === true));
    }
    if (candidates.length !== 1) return null;
    selected.push(candidates[0].id);
  }
  return new Set(selected).size === source.length ? selected : null;
}
