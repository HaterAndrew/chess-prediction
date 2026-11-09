import { cents } from "./types";

type Row = Record<string, unknown>;
const text = (value: unknown) => String(value ?? "").replace(/\s+/g, " ").trim();
const fields = ".invoicetname, .invoicekey, .invoicevaluesub, .invoicevalueextend";
const bodyTags = new Set(["div", "strong", "span", "br", "a", "p"]);
const signature = (event: string, section: string) => JSON.stringify([event, section]);

/** Prove the invoice contains exactly these player lines, never reading names. */
export async function invoiceContainsWholeOrder(html: string, expected: Row[], eventSubtotals?: Map<string, number>): Promise<boolean> {
  eventSubtotals?.clear();
  let unsafe = false;
  let roots = 0; let footers = 0; let markers = 0; let inside = 0;
  let buffer = ""; let active = false; let currentEvent = ""; let pendingPlayer = false;
  const lines: string[] = [];
  const lineEvents: string[] = [];
  const subtotals: number[] = [];
  let contribution: number | null = null; let grand: number | null = null;
  let awaiting: "subtotal" | "contribution" | "grand" | null = null;
  const consume = (kind: string, raw: string) => {
    const value = text(raw);
    if (kind === "invoicetname") {
      if (pendingPlayer || lines.length !== subtotals.length || contribution !== null || !value.startsWith("Tournamen Name:")) { unsafe = true; return; }
      currentEvent = value.slice("Tournamen Name:".length).trim();
    } else if (kind === "invoicekey") {
      if (value.startsWith("Player's Name:")) {
        if (!currentEvent || pendingPlayer || lines.length !== subtotals.length || contribution !== null) unsafe = true;
        pendingPlayer = true;
      } else if (value.startsWith("Section:")) {
        if (!pendingPlayer || !currentEvent) unsafe = true;
        lines.push(signature(currentEvent, value.slice("Section:".length).trim()));
        lineEvents.push(currentEvent);
        pendingPlayer = false;
      }
    } else if (kind === "invoicevaluesub") {
      const phase = value === "Sub Total" ? "subtotal" : value === "PayPal Contribution" ? "contribution" : value === "Grand Total" ? "grand" : null;
      if (phase) {
        if ((phase === "subtotal" && lines.length !== subtotals.length + 1)
            || (phase === "contribution" && lines.length !== subtotals.length)
            || awaiting || grand !== null || (phase === "subtotal" && contribution !== null)
            || (phase === "grand" && contribution === null)) unsafe = true;
        awaiting = phase;
      }
    } else if (kind === "invoicevalueextend") {
      const amount = /^US\s+\$\s*(\d[\d,]*(?:\.\d{1,2})?)$/.exec(value);
      if (!awaiting || !amount) { unsafe = true; return; }
      const paid = cents(amount[1]);
      if (awaiting === "subtotal") subtotals.push(paid);
      else if (awaiting === "contribution") { if (contribution !== null) unsafe = true; contribution = paid; }
      else { if (grand !== null) unsafe = true; grand = paid; }
      awaiting = null;
    }
  };
  await new HTMLRewriter().onDocument({ comments() { unsafe = true; } }).on("#invoicecontents", { element() { roots++; } })
    .on(".invoicefotter", { element() { footers++; } })
    // No scripts execute here. Refuse body tags that can hide later invoice
    // fields from parsing, including raw-text, foreign-content and template tags.
    .on("body *", { element(el) { if (!bodyTags.has(el.tagName)) unsafe = true; } })
    .on(fields.split(", ").map(s => `#invoicecontents ${s}`).join(", "), { element() { inside++; } })
    .on(fields, {
      element(el) {
        if (el.tagName !== "div") { unsafe = true; return; }
        if (active) unsafe = true;
        active = true; buffer = ""; markers++;
        const kind = el.getAttribute("class") ?? "";
        if (!["invoicetname", "invoicekey", "invoicevaluesub", "invoicevalueextend"].includes(kind)) unsafe = true;
        el.onEndTag(() => { consume(kind, buffer); active = false; });
      },
      text(chunk) { buffer += chunk.text; },
    }).transform(new Response(html)).text();
  if (unsafe || active || roots !== 1 || footers !== 1 || markers !== inside || pendingPlayer || awaiting
      || contribution === null || grand === null || lines.length !== subtotals.length
      || subtotals.reduce((a, b) => a + b, 0) + contribution !== grand) throw new Error("invoice_schema_changed");
  const totals = new Set(expected.map(r => cents(r.order_value)));
  if (totals.size !== 1 || !totals.has(grand)) throw new Error("order_reconciliation_failed");
  const wanted = expected.map(r => signature(text(r.tournament), text(r.section))).sort();
  if (lines.length !== wanted.length || JSON.stringify(lines.sort()) !== JSON.stringify(wanted)) return false;
  const contributions = new Set(expected.map(r => r.paypal_credit_card_fee_contribution ? cents(r.paypal_credit_card_fee_contribution) : 0).filter(n => n > 0));
  if (contributions.size > 1 || ([...contributions][0] ?? 0) !== contribution) throw new Error("order_reconciliation_failed");
  lineEvents.forEach((event, i) => eventSubtotals?.set(event, (eventSubtotals.get(event) ?? 0) + subtotals[i]));
  return true;
}
