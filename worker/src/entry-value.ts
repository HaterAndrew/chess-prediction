// Approximate dollar value of entries per live event: the organizer's view of
// upcoming card deposits. Pure: takes the site payload, returns figures.
//
// Paid entries (gross minus withdrawals) times the flyer's top-section fee.
// Entries registered on or before the early-bird deadline take the early-bird
// fee, read from the daily curve. Free, discounted and credit entries, lower
// section prices and processor fees are not modelled, so the figure runs high.

export interface ValueCard {
  family: string;
  year: number;
  status: string;
  current_count: number;
  withdrawal_count?: number | null;
  daily_data?: Array<[number, number]> | null;
  daily_start_date?: string | null;
  early_bird_fee?: number | null;
  early_bird_deadline?: string | null;
  regular_fee?: number | null;
  onsite_fee?: number | null;
}

export interface ValuePayload {
  generated: string;
  tournaments: ValueCard[];
}

// "early_bird": the early-bird / regular split applied. "regular": one fee for
// every entry. "onsite": only the at-the-door fee is posted.
export type FeeBasis = "early_bird" | "regular" | "onsite";

export interface LastDayValue {
  entries: number;
  value: number;
  span: number;
}

export interface EventValue {
  family: string;
  year: number;
  value: number | null;
  basis: FeeBasis | null;
  missing: "no_fee" | null;
  last_day: LastDayValue | null;
}

const DAY_MS = 86_400_000;

// Whole days from `startIso` to `iso`, both 'YYYY-MM-DD' calendar dates.
function daysBetween(startIso: string, iso: string): number | null {
  const a = Date.parse(`${startIso}T00:00:00Z`);
  const b = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.round((b - a) / DAY_MS);
}

function positive(n: number | null | undefined): number | null {
  return typeof n === "number" && Number.isFinite(n) && n > 0 ? n : null;
}

// Sorted, one point per day, cumulative totals that only rise and never pass
// the scraped count: the same rules as docs/daily_series.js sanitizeSeries.
export function cleanSeries(card: ValueCard): Array<[number, number]> {
  const byDay = new Map<number, number>();
  for (const pt of card.daily_data ?? []) {
    if (!Array.isArray(pt) || pt.length < 2) continue;
    const [day, val] = [Number(pt[0]), Number(pt[1])];
    if (!Number.isFinite(day) || !Number.isFinite(val) || day < 0 || val < 0) continue;
    byDay.set(day, Math.max(val, byDay.get(day) ?? 0));
  }
  const kept: Array<[number, number]> = [];
  for (const [day, val] of [...byDay].sort((x, y) => x[0] - y[0])) {
    if (val > card.current_count) continue;
    if (kept.length && val < kept[kept.length - 1][1]) continue;
    kept.push([day, val]);
  }
  return kept;
}

function countOnOrBefore(points: Array<[number, number]>, day: number): number {
  let n = 0;
  for (const [d, v] of points) {
    if (d > day) break;
    n = v;
  }
  return n;
}

interface FeePlan {
  basis: FeeBasis;
  base: number;
  earlyBird: number | null;
  deadlineDay: number | null;
}

// Which fees apply, or null when the flyer has posted none.
function feePlan(card: ValueCard, points: Array<[number, number]>): FeePlan | null {
  const regular = positive(card.regular_fee);
  if (regular === null) {
    const onsite = positive(card.onsite_fee);
    return onsite === null ? null : { basis: "onsite", base: onsite, earlyBird: null, deadlineDay: null };
  }
  const earlyBird = positive(card.early_bird_fee);
  const start = card.daily_start_date;
  const deadline = card.early_bird_deadline;
  const deadlineDay = start && deadline ? daysBetween(start, deadline) : null;
  // Without a dated curve there is no way to tell which entries beat the
  // deadline, so every entry is priced at the regular fee.
  if (earlyBird === null || deadlineDay === null || points.length === 0) {
    return { basis: "regular", base: regular, earlyBird: null, deadlineDay: null };
  }
  return { basis: "early_bird", base: regular, earlyBird, deadlineDay };
}

function feeOnDay(plan: FeePlan, day: number): number {
  return plan.earlyBird !== null && plan.deadlineDay !== null && day <= plan.deadlineDay
    ? plan.earlyBird
    : plan.base;
}

function valueSoFar(card: ValueCard, plan: FeePlan, points: Array<[number, number]>): number {
  const paid = Math.max(0, card.current_count - Math.max(0, card.withdrawal_count ?? 0));
  if (plan.earlyBird === null || plan.deadlineDay === null) return paid * plan.base;
  const early = Math.min(paid, countOnOrBefore(points, plan.deadlineDay));
  return early * plan.earlyBird + (paid - early) * plan.base;
}

// Entries in the curve's final interval, only when it ends on the payload's
// generated date (a tail that stopped days ago is not "last day").
function lastDay(
  card: ValueCard,
  plan: FeePlan,
  points: Array<[number, number]>,
  generated: string,
): LastDayValue | null {
  if (points.length < 2 || !card.daily_start_date) return null;
  const [prev, last] = [points[points.length - 2], points[points.length - 1]];
  if (daysBetween(card.daily_start_date, generated) !== last[0]) return null;
  const entries = last[1] - prev[1];
  return { entries, value: Math.round(entries * feeOnDay(plan, last[0])), span: last[0] - prev[0] };
}

export function eventValue(card: ValueCard, generated: string): EventValue {
  const points = cleanSeries(card);
  const plan = feePlan(card, points);
  const id = { family: card.family, year: card.year };
  if (plan === null) return { ...id, value: null, basis: null, missing: "no_fee", last_day: null };
  return {
    ...id,
    value: Math.round(valueSoFar(card, plan, points)),
    basis: plan.basis,
    missing: null,
    last_day: lastDay(card, plan, points, generated),
  };
}

export function entryValues(data: ValuePayload): EventValue[] {
  return data.tournaments
    .filter((t) => t.status === "live")
    .map((t) => eventValue(t, data.generated));
}
