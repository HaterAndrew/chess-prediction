import { allocateCents } from "./allocation";
import { normalizeFamily } from "./editions";
import { matchPublicRegistrations } from "./public-cohort";
import type { PublicRegistration } from "./public-cohort";
import { calendarDate, cents, cohortHash, sha256, INVOICE_DISCOUNT_VARIANT } from "./types";
import type { ReceiptBucket, ReceiptCard, ReceiptSnapshot, ReceiptSummary } from "./types";

type Row = Record<string, unknown>;
const DAY = 86_400_000;
const money = (value: unknown) => value === "" || value === null || value === undefined ? 0 : cents(value);
const text = (value: unknown) => typeof value === "string" ? value.trim() : typeof value === "number" ? String(value) : typeof value === "boolean" ? value ? "1" : "0" : "";
const deleted = (row: Row) => !["", "0", "No"].includes(text(row.is_deleted));
const freeRegistration = (r: Row) => text(r.status) === "Free Registration"
  && [r.section_amount, r.membership_amount, r.paypal_credit_card_fee_contribution, r.other_fees, r.order_value].every(v => money(v) === 0);
const manualCash = (r: Row) => text(r.status) === "Manual" && text(r.payment_type) === "0"
  && text(r.paypal_trans_id).toLowerCase() === "cash";

// An explicit Manual/Free entry is waived,
// even when its face fee and recorded order total remain positive.
const manualFree = (r: Row) => text(r.status) === "Manual" && text(r.payment_type) === "0"
  && text(r.paypal_trans_id).toLowerCase() === "free" && r.is_refunded === ""
  && [r.membership_amount, r.secmembership_amount, r.paypal_credit_card_fee_contribution, r.other_fees].every(v => money(v) === 0);

function paidAt(row: Row): string {
  const date = text(row.payment_date);
  const time = text(row.payment_time);
  if (!calendarDate(date) || !/^(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d$/.test(time)) throw new Error("payment_date_missing");
  const iso = `${date}T${time}Z`;
  if (!Number.isFinite(Date.parse(iso))) throw new Error("payment_date_missing");
  return iso;
}

export function orderKey(row: Row): string {
  const id = text(row.order_id);
  if (/^\d+$/.test(id)) return id;
  // Transaction IDs alone repeat in the source. Do not silently deduplicate them.
  const invoice = text(row.invoicenumber);
  const transaction = text(row.paypal_trans_id);
  if (!invoice || !transaction) throw new Error("order_identity_missing");
  return `${invoice}|${transaction}`;
}

function assertRow(row: Row): void {
  for (const field of ["status", "tournament", "section_amount", "membership_amount", "order_value", "is_deleted", "payment_date", "payment_time"]) {
    if (!(field in row)) throw new Error("source_schema_changed");
  }
  if (money(row.secmembership_amount) > 0) throw new Error("secondary_membership_requires_reconciliation");
  // Non-Declined is a query category, not proof of paid status. Unknown states
  // cannot be subtracted from a summary whose inclusion rules are unverified.
  if (text(row.status) !== "Approved" && !freeRegistration(row) && !manualCash(row) && !manualFree(row)) throw new Error("unreconciled_payment_status");
  if (/credit|transfer/i.test(text(row.paypal_trans_id)) && money(row.order_value)) throw new Error("credit_provenance_required");
  paidAt(row);
}

function belongs(row: Row, card: ReceiptCard): boolean {
  const parts = /^(\d{4})\s+(.+)$/.exec(text(row.tournament));
  return !!parts && Number(parts[1]) === card.year && normalizeFamily(parts[2]) === normalizeFamily(card.family);
}

/** Choose an identity column only by proving its hash matches the observed public set. */
async function sourceCohort(rows: Row[], card: ReceiptCard, loadPublic?: () => Promise<PublicRegistration[]>): Promise<ReceiptSnapshot["cohort"]> {
  if (!card.count_cohort_hash || !card.count_observed_at) return [];
  const registrations = rows.filter(r => !deleted(r));
  const fields = Object.keys(registrations[0] ?? {}).filter(k => /^(?:id|pid|player_id|registration_id|entry_id|player_tournament_id)$/i.test(k));
  const matches: ReceiptSnapshot["cohort"][] = [];
  for (const field of fields) {
    if (registrations.some(r => !/^\d+$/.test(text(r[field])))) continue;
    const cohort = await Promise.all(registrations.map(async row => ({ id: await sha256(text(row[field])), paid_at: paidAt(row) })));
    if (new Set(cohort.map(r => r.id)).size !== cohort.length) continue;
    const observed = cohort.filter(r => Date.parse(r.paid_at) <= Date.parse(card.count_observed_at!));
    if (observed.length === card.current_count && await cohortHash(observed.map(r => r.id)) === card.count_cohort_hash) matches.push(cohort);
  }
  if (!matches.length && loadPublic) {
    const ids = await matchPublicRegistrations(registrations, await loadPublic());
    if (ids && ids.length === registrations.length) {
      const cohort = await Promise.all(registrations.map(async (r, i) => ({ id: await sha256(ids[i]), paid_at: paidAt(r) })));
      const observed = cohort.filter(r => Date.parse(r.paid_at) <= Date.parse(card.count_observed_at!));
      if (observed.length === card.current_count && await cohortHash(observed.map(r => r.id)) === card.count_cohort_hash) matches.push(cohort);
    }
  }
  if (matches.length > 1 && matches.some(c => JSON.stringify(c) !== JSON.stringify(matches[0]))) throw new Error("ambiguous_registration_identity");
  return matches[0] ?? [];
}

export async function buildReceiptSnapshot(
  card: ReceiptCard, tournamentId: string, rows: Row[], summary: ReceiptSummary,
  sourceAsOf: string, loadOrder: (transaction: string, expected: Row[]) => Promise<Row[]>,
  loadPublic?: () => Promise<PublicRegistration[]>,
): Promise<ReceiptSnapshot> {
  if (!calendarDate(card.event_start) || (card.registration_close != null && !calendarDate(card.registration_close))) throw new Error("event_calendar_missing");
  rows.forEach(assertRow);
  if (rows.some(row => !belongs(row, card))) throw new Error("report_edition_mismatch");
  const discounts = (r: Row) => money(r.public_discount_amount) + money(r.discount_amount);
  const sectionSum = rows.reduce((n, r) => n + money(r.section_amount), 0);
  const discountSum = rows.reduce((n, r) => n + discounts(r), 0);
  // Both published layouts exist. The native financial summary must prove
  // which section-price convention is in use before any amount is accepted.
  const netSections = sectionSum === summary.entry_cents;
  // The live JSON report omits cart-discount amounts even when its summary
  // reports them. In that contract, derive net entry cash from complete paid
  // orders and reconcile the resulting event total below.
  const discountsOmitted = discountSum === 0 && sectionSum > summary.entry_cents;
  if (!netSections && !discountsOmitted && sectionSum - discountSum !== summary.entry_cents) throw new Error("entry_reconciliation_failed");
  const sourceEntry = (r: Row) => {
    const amount = money(r.section_amount) - (netSections ? 0 : discounts(r));
    if (amount < 0) throw new Error("discount_reconciliation_failed");
    return amount;
  };
  const cashEntries = new Map<Row, number>();
  const entry = (r: Row) => cashEntries.get(r) ?? sourceEntry(r);
  const cashWeight = (r: Row) => entry(r) + money(r.membership_amount) + money(r.other_fees);
  const eventKey = (r: Row) => text(r.tournament).replace(/^(\d{4})\s+(.+)$/, (_all, year, family) => `${year}|${normalizeFamily(family)}`);
  const signature = (r: Row) => JSON.stringify([eventKey(r), text(r.section), paidAt(r),
    money(r.section_amount), money(r.membership_amount), money(r.other_fees), money(r.public_discount_amount), money(r.discount_amount)]);
  const groups = new Map<string, Row[]>();
  for (const row of rows) {
    const key = orderKey(row);
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  const contribution = new Map<Row, number>();
  const orderReports = new Map<string, Promise<Row[]>>();
  let freeInvoiceDifference = 0;
  let invoiceDiscountTotal = 0;
  for (const [key, part] of groups) {
    const values = new Set(part.map(r => money(r.paypal_credit_card_fee_contribution)).filter(n => n > 0));
    const totals = new Set(part.map(r => money(r.order_value)));
    if (values.size > 1 || totals.size !== 1) throw new Error("order_reconciliation_failed");
    let totalContribution = [...values][0] ?? 0;
    let full = part;
    if ([...totals][0] > 0 || part.some(r => cashWeight(r) > 0)) {
      const transaction = part.map(r => text(r.paypal_trans_id)).find(Boolean) ?? "";
      if (!transaction || transaction.length > 200) throw new Error("shared_order_details_required");
      if (!orderReports.has(transaction)) {
        const expectedOrders = new Set(rows.filter(r => text(r.paypal_trans_id) === transaction).map(orderKey));
        orderReports.set(transaction, loadOrder(transaction, rows.filter(r => expectedOrders.has(orderKey(r)))));
      }
      full = (await orderReports.get(transaction)!).filter(r => orderKey(r) === key);
      full.forEach(assertRow);
      if (!full.length) throw new Error("shared_order_reconciliation_failed");
    }
    const fullContributions = new Set(full.map(r => money(r.paypal_credit_card_fee_contribution)).filter(n => n > 0));
    if (fullContributions.size > 1 || full.some(r => money(r.order_value) !== [...totals][0])) throw new Error("order_reconciliation_failed");
    totalContribution = [...fullContributions][0] ?? 0;
    // Reconcile the COMPLETE order's convention: another event can have a
    // discount even when this target event's raw/net figures are identical.
    const rawCash = (r: Row) => money(r.section_amount) + money(r.membership_amount) + money(r.other_fees);
    const fullRaw = full.reduce((n, r) => n + rawCash(r), 0);
    const fullDiscounts = full.reduce((n, r) => n + discounts(r), 0);
    const freeOnlyOrder = full.every(manualFree);
    if (full.some(manualFree) && !freeOnlyOrder) throw new Error("shared_order_reconciliation_failed");
    const hasInvoice = full.some(r => r.invoice_event_subtotal_cents !== undefined);
    if (hasInvoice && (full.some(r => !Number.isSafeInteger(r.invoice_event_subtotal_cents) || Number(r.invoice_event_subtotal_cents) < 0)
        || new Set(full.map(paidAt)).size !== 1)) throw new Error("order_reconciliation_failed");
    let netOrderTotal = [...totals][0];
    if (full.some(r => r.invoice_discount_variant !== undefined || r.invoice_discount_cents !== undefined || r.invoice_net_order_cents !== undefined)) {
      const row = full[0];
      const gap = row.invoice_discount_cents;
      const net = row.invoice_net_order_cents;
      if (full.length !== 1 || !belongs(row, card) || row.status !== "Approved" || row.invoice_discount_variant !== INVOICE_DISCOUNT_VARIANT
          || !Number.isSafeInteger(gap) || Number(gap) <= 0 || !hasInvoice || !Number.isSafeInteger(net) || Number(net) < 0
          || Number(net) + Number(gap) !== [...totals][0] || Number(row.invoice_event_subtotal_cents) + totalContribution !== net) {
        throw new Error("invoice_schema_changed");
      }
      invoiceDiscountTotal += Number(gap);
      netOrderTotal = Number(net);
    }
    const expectedCash = freeOnlyOrder ? 0 : netOrderTotal - totalContribution;
    const subtract = fullRaw !== expectedCash;
    const cashOnlyOrder = full.some(manualCash) && full.every(r => manualCash(r) || freeRegistration(r));
    const manualCorrection = (cashOnlyOrder || freeOnlyOrder) && full.every(r => belongs(r, card));
    const inferDiscount = !cashOnlyOrder && !freeOnlyOrder && fullDiscounts === 0 && fullRaw > expectedCash;
    if (freeOnlyOrder) {
      const subtotals = new Set(full.map(r => hasInvoice ? Number(r.invoice_event_subtotal_cents) : money(r.order_value)));
      if (subtotals.size !== 1) throw new Error("order_reconciliation_failed");
      freeInvoiceDifference += [...subtotals][0];
    }
    if ((cashOnlyOrder || freeOnlyOrder) && !manualCorrection) throw new Error("shared_order_reconciliation_failed");
    const distributeEntry = hasInvoice || manualCorrection || inferDiscount;
    if (distributeEntry) {
      if (manualCorrection && full.length !== part.length) throw new Error("shared_order_reconciliation_failed");
      const allocation = new Map<string, number>();
      const groups = new Map<string, Array<{ row: Row; index: number }>>();
      full.forEach((row, index) => {
        const event = hasInvoice ? text(row.tournament).replace(/\s+/g, " ") : "order";
        groups.set(event, [...(groups.get(event) ?? []), { row, index }]);
      });
      let invoiceCash = 0;
      for (const lines of groups.values()) {
        const eventRows = lines.map(line => line.row);
        const values = new Set(eventRows.map(r => Number(r.invoice_event_subtotal_cents)));
        if (hasInvoice && values.size !== 1) throw new Error("order_reconciliation_failed");
        const subtotal = freeOnlyOrder ? 0 : hasInvoice ? [...values][0] : expectedCash;
        invoiceCash += subtotal;
        const nonEntryCash = eventRows.reduce((n, r) => n + money(r.membership_amount) + money(r.other_fees), 0);
        const receivedEntryCash = subtotal - nonEntryCash;
        const faceEntry = eventRows.reduce((n, r) => n + sourceEntry(r), 0);
        if (receivedEntryCash < 0 || receivedEntryCash > faceEntry) throw new Error("shared_order_reconciliation_failed");
        const eventAllocation = allocateCents(receivedEntryCash, lines.map(({ row, index }) => ({ id: `${signature(row)}|${index}`, cash: sourceEntry(row) })));
        for (const [id, amount] of eventAllocation) allocation.set(id, amount);
      }
      if (hasInvoice && invoiceCash !== expectedCash) throw new Error("order_reconciliation_failed");
      const amounts = new Map<string, number[]>();
      full.forEach((r, i) => {
        const id = signature(r);
        amounts.set(id, [...(amounts.get(id) ?? []), allocation.get(`${id}|${i}`)!]);
        cashEntries.set(r, allocation.get(`${id}|${i}`)!);
      });
      for (const r of part) {
        const values = amounts.get(signature(r));
        if (!values?.length) throw new Error("shared_order_line_missing");
        cashEntries.set(r, values.shift()!);
      }
    } else if (expectedCash < 0 || (subtract && fullRaw - fullDiscounts !== expectedCash)) throw new Error("shared_order_reconciliation_failed");
    // This proof identifies the entire single-player, single-event order.
    // Its contribution has an owner even when the entry is fully discounted.
    if (full.length === 1 && part.length === 1 && full[0].invoice_discount_variant === INVOICE_DISCOUNT_VARIANT) {
      contribution.set(part[0], totalContribution);
      continue;
    }
    const originalCash = (r: Row) => {
      const cash = distributeEntry ? entry(r) + money(r.membership_amount) + money(r.other_fees)
        : rawCash(r) - (subtract ? discounts(r) : 0);
      if (cash < 0) throw new Error("discount_reconciliation_failed");
      return cash;
    };
    // Event identity, rather than response array position, owns residual cents.
    const eventWeights = new Map<string, number>();
    full.forEach(r => eventWeights.set(eventKey(r), (eventWeights.get(eventKey(r)) ?? 0) + originalCash(r)));
    const eventAllocation = allocateCents(totalContribution, [...eventWeights].map(([id, cash]) => ({ id, cash })));
    const targetRows = full.filter(r => belongs(r, card));
    const lineWeights = new Map<string, number>();
    targetRows.forEach(r => lineWeights.set(signature(r), (lineWeights.get(signature(r)) ?? 0) + originalCash(r)));
    const lineAllocation = allocateCents(eventAllocation.get(eventKey(part[0])) ?? 0,
      [...lineWeights].map(([id, cash]) => ({ id, cash })));
    const amounts = new Map<string, number[]>();
    for (const id of lineWeights.keys()) {
      const count = targetRows.filter(r => signature(r) === id).length;
      const allocated = lineAllocation.get(id)!;
      amounts.set(id, Array.from({ length: count }, (_, i) => Math.floor(allocated / count) + (i < allocated % count ? 1 : 0)));
    }
    for (const r of part) {
      const list = amounts.get(signature(r));
      if (!list?.length) throw new Error("shared_order_line_missing");
      contribution.set(r, list.shift()!);
    }
  }
  const buckets = new Map<number, ReceiptBucket>();
  for (const row of rows) {
    const days = (Date.parse(card.event_start + "T00:00:00Z") - Date.parse(paidAt(row))) / DAY;
    const bucket = buckets.get(days) ?? { days_before: days, registrations: 0, entry_cents: 0, membership_cents: 0, contribution_cents: 0, other_cents: 0 };
    bucket.registrations += deleted(row) ? 0 : 1;
    bucket.entry_cents += entry(row);
    bucket.membership_cents += money(row.membership_amount);
    bucket.contribution_cents += contribution.get(row) ?? 0;
    bucket.other_cents += money(row.other_fees);
    buckets.set(days, bucket);
  }
  const recordedEntry = [...buckets.values()].reduce((n, b) => n + b.entry_cents, 0);
  const manualFaceDifference = rows.filter(manualCash).reduce((n, r) => n + sourceEntry(r) - entry(r), 0);
  const freeFaceDifference = rows.filter(manualFree).reduce((n, r) => n + sourceEntry(r) - entry(r), 0);
  const manualAdjustment = summary.entry_cents - recordedEntry;
  // Native cash may already be net while waived orders still appear at face
  // or invoice price. Prove the two adjustments independently; never attribute
  // an unexplained or ambiguous native-summary gap to an arbitrary correction.
  const corrections = [...new Set([0, manualFaceDifference])].flatMap(cash =>
    [...new Set([0, freeFaceDifference, freeInvoiceDifference])].map(free => ({ cash, free })))
    .filter(({ cash, free }) => cash >= 0 && free >= 0 && cash + free === manualAdjustment);
  if (corrections.length !== 1) throw new Error("receipt_reconciliation_failed");
  const correction = corrections[0];
  const receivedSummary = { ...summary, entry_cents: recordedEntry, net_cents: summary.net_cents - manualAdjustment };
  for (const field of ["entry_cents", "membership_cents", "contribution_cents", "other_cents"] as const) {
    if ([...buckets.values()].reduce((n, b) => n + b[field], 0) !== receivedSummary[field]) throw new Error("receipt_reconciliation_failed");
  }
  return {
    schema: 1, family: card.family, year: card.year, tournament_id: tournamentId, source_as_of: sourceAsOf,
    event_start: card.event_start, registration_close: card.registration_close ?? null,
    regular_fee_cents: typeof card.regular_fee === "number" && card.regular_fee > 0 ? cents(card.regular_fee) : null,
    registration_count: rows.filter(r => !deleted(r)).length,
    summary: receivedSummary,
    ...(manualAdjustment ? { native_summary: summary, manual_cash_adjustment_cents: correction.cash,
      manual_free_adjustment_cents: correction.free } : {}),
    ...(invoiceDiscountTotal ? { invoice_discount_variant: INVOICE_DISCOUNT_VARIANT,
      invoice_discount_cents: invoiceDiscountTotal } : {}),
    cohort: await sourceCohort(rows, card, loadPublic), buckets: [...buckets.values()],
    previous_net_cents: null, previous_as_of: null,
  };
}
