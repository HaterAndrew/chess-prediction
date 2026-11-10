import { matchTournament, normalizeFamily } from "./editions";
import { calendarDate } from "./types";
import type { ReceiptCard } from "./types";

type EditionCard = Pick<ReceiptCard, "family" | "year" | "event_start">;

/** Yearless source names require an independent exact source-calendar join. */
export async function resolveTournament(card: EditionCard, options: Array<{ id: string; title: string }>,
  readSettings: (id: string) => Promise<string>): Promise<string> {
  try { return matchTournament(card, options); }
  catch (error) { if (!(error instanceof Error) || error.message !== "unmapped_tournament") throw error; }
  const candidates = options.filter(o => !/^\d{4}\s/.test(o.title.trim()) && normalizeFamily(o.title) === normalizeFamily(card.family));
  if (candidates.length !== 1) throw new Error(candidates.length ? "ambiguous_tournament" : "unmapped_tournament");
  if (!calendarDate(card.event_start)) throw new Error("incompatible_edition");
  const id = candidates[0].id;
  if (!/^\d{1,12}$/.test(id)) throw new Error("source_schema_changed");
  const fields = new Map<string, string[]>();
  await new HTMLRewriter().on('input[name="tid"], input[name="tourid"], input[name="tname"], input[name="startson"]', {
    element(el) {
      const name = el.getAttribute("name")!;
      fields.set(name, [...(fields.get(name) ?? []), el.getAttribute("value") ?? ""]);
    },
  }).transform(new Response(await readSettings(id))).text();
  if (["tid", "tourid", "tname", "startson"].some(name => fields.get(name)?.length !== 1)) throw new Error("source_schema_changed");
  const value = (name: string) => fields.get(name)![0];
  if (value("tid") !== id || value("tourid") !== id || !calendarDate(value("startson"))
      || value("startson") !== card.event_start || Number(value("startson").slice(0, 4)) !== card.year
      || normalizeFamily(value("tname")) !== normalizeFamily(card.family)) throw new Error("incompatible_edition");
  return id;
}
