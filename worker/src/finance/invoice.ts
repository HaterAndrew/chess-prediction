import { cents, INVOICE_DISCOUNT_VARIANT } from "./types";

import type { InvoiceDiscountEvidence } from "./types";

type Row = Record<string, unknown>;
const text = (value: unknown) => String(value ?? "").replace(/\s+/g, " ").trim();
const fields = ".invoicetname, .invoicekey, .invoicevaluesub, .invoicevalueextend";
const bodyTags = new Set(["div", "strong", "span", "br", "a", "p"]);
const signature = (event: string, section: string) => JSON.stringify([event, section]);

/** Prove the invoice contains exactly these player lines, never reading names. */
export async function invoiceContainsWholeOrder(html: string, expected: Row[], eventSubtotals?: Map<string, number>, discountEvidence?: Map<string, InvoiceDiscountEvidence>): Promise<boolean> {
  eventSubtotals?.clear();
  discountEvidence?.clear();
  let unsafe = false;
  let bodyRoots = 0; let bodyMarkers = 0;
  let roots = 0; let footers = 0; let markers = 0; let inside = 0;
  let bodyText = "";
  let buffer = ""; let active = false; let currentEvent = ""; let pendingPlayer = false;
  const lines: string[] = [];
  const lineEvents: string[] = [];
  const subtotals: number[] = [];
  const discounts = new Map<number, number>();
  let discountLine: number | null = null;
  let discountValid = true;
  let contribution: number | null = null; let grand: number | null = null;
  let awaiting: "subtotal" | "contribution" | "grand" | null = null;
  const consume = (kind: string, raw: string) => {
    const value = text(raw);
    if (discountLine !== null && kind !== "invoicevaluesub") { discountValid = false; discountLine = null; }
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
      } else if (/^Discount\b(?!.*\bcode\b)/i.test(value)) {
        if (pendingPlayer || awaiting || lines.length !== subtotals.length + 1 || contribution !== null
            || discountLine !== null || discounts.has(lines.length - 1)) discountValid = false;
        discountLine = lines.length - 1;
      }
    } else if (kind === "invoicevaluesub") {
      if (discountLine !== null) {
        const amount = /^(-\s*)?US\s+(-\s*)?\$\s*(-\s*)?(\d[\d,]*(?:\.\d{1,2})?)$/.exec(value);
        if (!amount || amount.slice(1, 4).filter(Boolean).length > 1) discountValid = false;
        else {
          // Informational discount evidence never changes balanced invoices.
          // An unusable amount can only deny the optional subtotal correction.
          try { discounts.set(discountLine, cents(amount[4])); }
          catch { discountValid = false; }
        }
        discountLine = null;
      }
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
  await new HTMLRewriter().on("body", { text(chunk) { bodyText += chunk.text + (chunk.lastInTextNode ? "\n" : ""); } }).onDocument({ comments() { unsafe = true; } }).on("#invoicecontents", { element() { roots++; } })
    .on("body #invoicecontents", { element() { bodyRoots++; } })
    .on(fields.split(", ").map(s => `body #invoicecontents ${s}`).join(", "), { element() { bodyMarkers++; } })
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
      || contribution === null || grand === null || lines.length !== subtotals.length) throw new Error("invoice_schema_changed");
  const totals = new Set(expected.map(r => cents(r.order_value)));
  if (totals.size !== 1 || !totals.has(grand)) throw new Error("order_reconciliation_failed");
  const wanted = expected.map(r => signature(text(r.tournament), text(r.section))).sort();
  if (lines.length !== wanted.length || JSON.stringify(lines.sort()) !== JSON.stringify(wanted)) return false;
  const contributions = new Set(expected.map(r => r.paypal_credit_card_fee_contribution ? cents(r.paypal_credit_card_fee_contribution) : 0).filter(n => n > 0));
  if (contributions.size > 1 || ([...contributions][0] ?? 0) !== contribution) throw new Error("order_reconciliation_failed");
  const displayed = subtotals.reduce((a, b) => a + b, 0);
  const gap = grand - displayed - contribution;
  if (gap !== 0) {
    // Use the verified net subtotal after a claimed discount. The recorded
    // order and printed Grand Total remain gross in this source variant.
    // Only the complete one-player, one-event Approved cart proves this basis.
    const row = expected[0];
    const money = (v: unknown) => v === "" || v === null || v === undefined ? 0 : cents(v);
    // The correction must not mask a foreign line whose marker classes changed.
    // Count semantic line markers across the complete body independently of classes.
    // Unlabelled metadata is not evidence of a financial field.
    const body = text(bodyText);
    const semantic = [/Tournamen\s+Name\s*:/gi, /Player's\s+Name\s*:/gi, /Section\s*:/gi,
      /Sub\s+Total\b/gi, /PayPal\s+Contribution\b/gi, /Grand\s+Total\b/gi];
    const completeBody = semantic.every(pattern => (body.match(pattern) ?? []).length === 1);
    if (bodyRoots !== 1 || bodyMarkers !== markers || !completeBody || !discountValid || discountLine !== null || gap <= 0 || lines.length !== 1 || expected.length !== 1 || discounts.size !== 1 || discounts.get(0) !== gap
        || row.status !== "Approved" || !/^\d+$/.test(String(row.order_id ?? ""))
        || !["section_amount", "membership_amount", "other_fees"].every(k => k in row)
        || ["section_amount", "membership_amount", "other_fees"].reduce((n, k) => n + money(row[k]), 0) + contribution !== grand) {
      throw new Error("invoice_schema_changed");
    }
    eventSubtotals?.set(lineEvents[0], displayed);
    discountEvidence?.set(lineEvents[0], { variant: INVOICE_DISCOUNT_VARIANT, discount_cents: gap, net_order_cents: grand - gap });
  } else {
    lineEvents.forEach((event, i) => eventSubtotals?.set(event, (eventSubtotals.get(event) ?? 0) + subtotals[i]));
  }
  return true;
}
