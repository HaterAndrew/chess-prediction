// Join source registrations to public list IDs using unique federation IDs.
// Names and contact details are not needed or retained.
export interface PublicRegistration { id: string; uscf: string; fide: string }

export async function parsePublicRegistrations(html: string): Promise<PublicRegistration[]> {
  interface Cell { tag: string; text: string }
  interface Row { id: string | null; cells: Cell[]; cell: Cell | null }
  const stack: Row[] = [];
  const rows: PublicRegistration[] = [];
  let headerVerified = false;
  const expected = ["player's name", "player's name", "fide id", "fide rating", "uscf id", "uscf rating", "state", "section", "schedule", "bye(s)"];
  const clean = (v: string) => v.replace(/\s+/g, " ").trim().toLowerCase();
  const rewriter = new HTMLRewriter().on("tr", {
    element(el) {
      const row: Row = { id: null, cells: [], cell: null };
      stack.push(row);
      el.onEndTag(() => {
        if (stack.pop() !== row) throw new Error("public_registration_schema_changed");
        const headers = row.cells.filter(c => c.tag === "th").map(c => clean(c.text));
        if (headers.length === expected.length && headers.every((v, i) => v === expected[i])) headerVerified = true;
        if (!row.id) return;
        const cells = row.cells.filter(c => c.tag === "td");
        if (cells.length !== 10) throw new Error("public_registration_schema_changed");
        const uscf = clean(cells[4].text);
        const fide = /^\s*([1-9]\d{2,11})\b/.exec(cells[2].text)?.[1] ?? "";
        rows.push({ id: row.id, uscf: /^[1-9]\d{7}$/.test(uscf) ? uscf : "", fide });
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
  return rows;
}

/** Every source row must map uniquely. The model's cohort hash then proves the set. */
export function matchPublicRegistrations(source: Record<string, unknown>[], publicRows: PublicRegistration[]): string[] | null {
  if (source.length > publicRows.length) return null;
  const selected: string[] = [];
  for (const row of source) {
    const uscf = String(row.uscf_id ?? "").trim();
    const fide = String(row.fide_id ?? "").trim();
    const candidates = /^[1-9]\d{7}$/.test(uscf) ? publicRows.filter(p => p.uscf === uscf)
      : /^[1-9]\d{2,11}$/.test(fide) ? publicRows.filter(p => p.fide === fide) : [];
    if (candidates.length !== 1) return null;
    selected.push(candidates[0].id);
  }
  return new Set(selected).size === source.length ? selected : null;
}
