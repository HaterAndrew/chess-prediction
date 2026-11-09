import { cents, reconcileSummary } from "./types";
import type { ReceiptSummary } from "./types";

const SUMMARY_COLUMNS = [
  "Tournament fees ($) [Cart Discounts deducted]", "Primary membership fees ($)",
  "PayPal/Credit Card Fee Contributions ($)", "Other fees ($)", "Refunded ($)", "Gross Revenue ($)",
];

export async function parseSummary(html: string): Promise<ReceiptSummary> {
  const headers: string[] = [];
  const values: string[] = [];
  let buffer = "";
  await new HTMLRewriter().on("th, td", {
    element(el) {
      const target = el.tagName === "th" ? headers : values;
      buffer = "";
      el.onEndTag(() => { target.push(buffer.replace(/\s+/g, " ").trim()); });
    },
    text(chunk) { buffer += chunk.text; },
  }).transform(new Response(html)).text();
  if (headers.length < 6 || SUMMARY_COLUMNS.some((h, i) => headers[i] !== h) || values.length !== headers.length) {
    throw new Error("summary_schema_changed");
  }
  const n = values.slice(0, 6).map(cents);
  const result: ReceiptSummary = {
    entry_cents: n[0], membership_cents: n[1], contribution_cents: n[2], other_cents: n[3],
    refunded_cents: n[4], net_cents: n[5],
  };
  reconcileSummary(result);
  return result;
}

export async function tournamentOptions(html: string): Promise<Array<{ id: string; title: string }>> {
  const result: Array<{ id: string; title: string }> = [];
  let id = "";
  let title = "";
  await new HTMLRewriter().on("#tournments option", {
    element(el) {
      id = el.getAttribute("value") ?? ""; title = "";
      el.onEndTag(() => { if (/^\d+$/.test(id)) result.push({ id, title: title.trim() }); });
    },
    text(chunk) { title += chunk.text; },
  }).transform(new Response(html)).text();
  if (!result.length) throw new Error("tournament_schema_changed");
  return result;
}
