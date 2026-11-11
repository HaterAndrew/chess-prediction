import type { ChessActionClient } from "./client";
import { acquireRegistrations } from "./registrations";
import { matchPublicRegistrations, type PublicRegistration } from "./public-cohort";

/** Request-local references only: never added to registration storage or RPC. */
export interface RegistrationLink { id: string; order_id: string | null; section: string }

export async function acquireRegistrationLinks(client: Pick<ChessActionClient, "request">,
  card: { family: string; year: number }, tournamentId: string, sourceAsOf: string): Promise<RegistrationLink[]> {
  const links: RegistrationLink[] = [];
  // Reuse complete active/withdrawn pagination, exact source tournament IDs,
  // duplicate rejection and the two final count fences.
  await acquireRegistrations(client, card, tournamentId, sourceAsOf, (id, row) => {
    const order = row.order_id == null || row.order_id === "" ? null : String(row.order_id);
    if (order !== null && !/^\d{1,40}$/.test(order)
        || typeof row.section_menu_name !== "string" || row.section_menu_name.length > 240
        || /[\r\n]/.test(row.section_menu_name)) throw new Error("registration_schema_changed");
    links.push({ id, order_id: order, section: row.section_menu_name.trim() });
  });
  return links;
}

/** Prove the current native/public ID set before using an order reference. */
export async function matchRegistrationLinks(source: Record<string, unknown>[], links: RegistrationLink[],
  publicRows: PublicRegistration[]): Promise<string[] | null> {
  const publicIds = new Set(publicRows.map(r => r.id));
  if (links.length !== publicRows.length || new Set(links.map(r => r.id)).size !== links.length
      || publicIds.size !== publicRows.length || links.some(r => !publicIds.has(r.id))) return null;
  const selected: string[] = [];
  for (const row of source) {
    const direct = await matchPublicRegistrations([row], publicRows);
    if (direct) { selected.push(direct[0]); continue; }
    const order = String(row.order_id ?? "").trim();
    const section = String(row.section ?? "").trim();
    if (!/^\d{1,40}$/.test(order)) return null;
    const candidates = links.filter(r => r.order_id === order && r.section === section);
    if (candidates.length !== 1) return null;
    selected.push(candidates[0].id);
  }
  return new Set(selected).size === source.length ? selected : null;
}
