// Residual order-level receipts follow original cash charges, never player names.
// Refunds reuse the original allocation; discount/credit balances are not cash.
export function allocateCents(total: number, weights: Array<{ id: string; cash: number }>): Map<string, number> {
  if (!Number.isSafeInteger(total) || total < 0 || !weights.length
      || new Set(weights.map(w => w.id)).size !== weights.length
      || weights.some(w => !w.id || !Number.isSafeInteger(w.cash) || w.cash < 0)) throw new Error("invalid_allocation");
  const sum = weights.reduce((n, w) => n + w.cash, 0);
  if (!Number.isSafeInteger(sum) || (!sum && total)) throw new Error("unattributed_receipt");
  const rows = weights.map(w => {
    const product = BigInt(total) * BigInt(w.cash);
    const divisor = BigInt(sum || 1);
    return { id: w.id, cents: Number(product / divisor), remainder: product % divisor };
  });
  rows.sort((a, b) => a.remainder === b.remainder ? a.id.localeCompare(b.id) : a.remainder > b.remainder ? -1 : 1);
  const leftover = total - rows.reduce((n, r) => n + r.cents, 0);
  rows.forEach((r, i) => { if (i < leftover) r.cents++; });
  return new Map(rows.map(r => [r.id, r.cents]));
}
