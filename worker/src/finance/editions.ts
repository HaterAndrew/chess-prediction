import aliases from "./aliases.json";
import type { ReceiptCard } from "./types";

export function normalizeFamily(name: string): string {
  const stripped = name.replace(/\s*\(\s*in\s+[^)]+\)\s*$/i, "").trim()
    .replaceAll("Championshps", "Championships").replaceAll("Championsips", "Championships")
    .replaceAll("Cahmpionships", "Championships").replaceAll("Chess Congess", "Chess Congress");
  const normalized = stripped.replaceAll(",", "").replace(/\s+/g, " ").toLowerCase();
  const entry = Object.entries(aliases).find(([key]) => key.replaceAll(",", "").replace(/\s+/g, " ").toLowerCase() === normalized);
  return (entry?.[1] ?? stripped).replaceAll(",", "").replace(/\s+/g, " ").toLowerCase();
}

export function matchTournament(card: Pick<ReceiptCard, "family" | "year">, options: Array<{ id: string; title: string }>): string {
  if (card.year < 2023 && /world open.*(?:top 6|lower sections)/i.test(card.family)) throw new Error("incompatible_edition");
  const matches = options.filter(option => {
    const parts = /^(\d{4})\s+(.+)$/.exec(option.title.trim());
    return parts && Number(parts[1]) === card.year && normalizeFamily(parts[2]) === normalizeFamily(card.family);
  });
  if (matches.length !== 1) throw new Error(matches.length ? "ambiguous_tournament" : "unmapped_tournament");
  return matches[0].id;
}
