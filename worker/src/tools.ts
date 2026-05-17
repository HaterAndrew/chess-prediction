import type Anthropic from "@anthropic-ai/sdk";

export const CODE_EXECUTION_TOOL: Anthropic.Beta.Messages.BetaCodeExecutionTool20260120 = {
  type: "code_execution_20260120",
  name: "code_execution",
};

export interface Tournament {
  family: string;
  year: number;
  event_start: string | null;
  event_end: string | null;
  early_bird_deadline?: string | null;
  early_bird_fee?: number | null;
  regular_fee?: number | null;
  onsite_fee?: number | null;
  current_count?: number | null;
  gross_count?: number | null;
  withdrawal_count?: number | null;
  days_remaining?: number | null;
  point_estimate?: number | null;
  ci_lower?: number | null;
  ci_upper?: number | null;
  ci_level?: number | null;
  status?: string;
  prediction_tier?: string;
  low_confidence?: boolean;
  prediction_source?: string;
  n_historical_editions?: number;
  historical?: Array<{ year: number; count: number; family: string }>;
  daily_data?: Array<[number, number]>;
  registration_curve?: unknown;
  prior_year_pace?: Record<string, unknown> | null;
  city?: string;
  state?: string;
}

export interface WebsiteData {
  generated: string;
  generated_time?: string;
  model?: string;
  model_description?: string;
  tournaments: Tournament[];
}

export function tournamentId(t: Tournament): string {
  return `${t.family} ${t.year}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function pickCondensed(t: Tournament) {
  return {
    id: tournamentId(t),
    name: `${t.family} ${t.year}`,
    family: t.family,
    year: t.year,
    status: t.status ?? null,
    current_count: t.current_count ?? null,
    point_estimate: t.point_estimate ?? null,
    ci_lower: t.ci_lower ?? null,
    ci_upper: t.ci_upper ?? null,
    event_start: t.event_start ?? null,
    event_end: t.event_end ?? null,
    days_remaining: t.days_remaining ?? null,
  };
}

function scoreMatch(query: string, t: Tournament): number {
  const q = query.toLowerCase().trim();
  if (!q) return 0;
  const name = `${t.family} ${t.year}`.toLowerCase();
  const family = t.family.toLowerCase();
  const id = tournamentId(t);
  if (name === q || id === q) return 100;
  if (family === q) return 60;
  if (family.startsWith(q)) return 30;
  if (id.startsWith(q.replace(/\s+/g, "-"))) return 25;
  if (family.includes(q)) return 15;
  if (name.includes(q)) return 10;
  const tokens = q.split(/\s+/).filter(Boolean);
  if (tokens.length > 1 && tokens.every((tok) => name.includes(tok))) return 8;
  return 0;
}

export interface SearchArgs {
  query?: string;
  status?: string;
  year?: number;
  family?: string;
  limit?: number;
}

export function searchTournaments(data: WebsiteData, args: SearchArgs): unknown {
  const limit = Math.min(Math.max(args.limit ?? 20, 1), 50);
  let results = data.tournaments;
  if (args.status) results = results.filter((t) => (t.status ?? "").toLowerCase() === args.status!.toLowerCase());
  if (typeof args.year === "number") results = results.filter((t) => t.year === args.year);
  if (args.family) {
    const f = args.family.toLowerCase();
    results = results.filter((t) => t.family.toLowerCase().includes(f));
  }
  if (args.query && args.query.trim()) {
    const q = args.query;
    const scored = results
      .map((t) => ({ t, s: scoreMatch(q, t) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s);
    results = scored.slice(0, limit).map((x) => x.t);
  } else {
    results = results.slice(0, limit);
  }
  return { count: results.length, tournaments: results.map(pickCondensed) };
}

export function getTournament(data: WebsiteData, args: { id?: string; name?: string }): unknown {
  const key = (args.id ?? args.name ?? "").toLowerCase().trim();
  if (!key) return { error: "Provide id or name." };
  const direct = data.tournaments.find((t) => tournamentId(t) === key);
  let hit = direct;
  if (!hit) {
    const scored = data.tournaments
      .map((t) => ({ t, s: scoreMatch(key, t) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s);
    hit = scored[0]?.t;
  }
  if (!hit) return { error: `No tournament matched "${key}".` };
  const { registration_curve: _drop, ...full } = hit;
  void _drop;
  return {
    id: tournamentId(hit),
    name: `${hit.family} ${hit.year}`,
    ...full,
  };
}

const TOP_FIELDS = new Set([
  "point_estimate",
  "current_count",
  "ci_upper",
  "ci_lower",
  "days_remaining",
  "early_bird_fee",
  "regular_fee",
  "withdrawal_count",
]);

export function topTournaments(
  data: WebsiteData,
  args: { field?: string; n?: number; status?: string; year?: number; ascending?: boolean }
): unknown {
  const field = (args.field ?? "point_estimate") as keyof Tournament;
  if (!TOP_FIELDS.has(field as string)) {
    return { error: `Unsupported field "${field}". Use one of: ${[...TOP_FIELDS].join(", ")}.` };
  }
  const n = Math.min(Math.max(args.n ?? 5, 1), 20);
  let rows = data.tournaments;
  if (args.status) rows = rows.filter((t) => (t.status ?? "").toLowerCase() === args.status!.toLowerCase());
  if (typeof args.year === "number") rows = rows.filter((t) => t.year === args.year);
  rows = rows.filter((t) => typeof (t as unknown as Record<string, unknown>)[field as string] === "number");
  const dir = args.ascending ? 1 : -1;
  rows = [...rows].sort((a, b) => {
    const av = (a as unknown as Record<string, number>)[field as string];
    const bv = (b as unknown as Record<string, number>)[field as string];
    return (av - bv) * dir;
  });
  return {
    field,
    n,
    ascending: !!args.ascending,
    results: rows.slice(0, n).map((t) => ({
      ...pickCondensed(t),
      value: (t as unknown as Record<string, number>)[field as string],
    })),
  };
}

export function historicalForFamily(data: WebsiteData, args: { family?: string; n_years?: number }): unknown {
  if (!args.family) return { error: "Provide family." };
  const f = args.family.toLowerCase();
  const matches = data.tournaments.filter((t) => t.family.toLowerCase() === f);
  if (matches.length === 0) {
    const candidates = [...new Set(data.tournaments.map((t) => t.family))]
      .filter((name) => name.toLowerCase().includes(f))
      .slice(0, 10);
    return { error: `No exact match for family "${args.family}".`, candidates };
  }
  const points = new Map<number, number>();
  for (const t of matches) {
    if (typeof t.current_count === "number") points.set(t.year, t.current_count);
    if (Array.isArray(t.historical)) {
      for (const h of t.historical) points.set(h.year, h.count);
    }
  }
  const sorted = [...points.entries()].sort((a, b) => b[0] - a[0]);
  const nYears = Math.min(Math.max(args.n_years ?? 5, 1), 20);
  const top = sorted.slice(0, nYears).sort((a, b) => a[0] - b[0]);
  return {
    family: matches[0].family,
    series: top.map(([year, count]) => ({ year, count })),
  };
}

export function compareYears(
  data: WebsiteData,
  args: { family?: string; year_a?: number; year_b?: number }
): unknown {
  if (!args.family || typeof args.year_a !== "number" || typeof args.year_b !== "number") {
    return { error: "Provide family, year_a, year_b." };
  }
  const hist = historicalForFamily(data, { family: args.family, n_years: 20 }) as {
    family?: string;
    series?: Array<{ year: number; count: number }>;
    error?: string;
  };
  if (hist.error || !hist.series) return hist;
  const a = hist.series.find((p) => p.year === args.year_a);
  const b = hist.series.find((p) => p.year === args.year_b);
  if (!a && !b) return { error: `No data for either ${args.year_a} or ${args.year_b}.` };
  let delta: number | null = null;
  let pct: number | null = null;
  if (a && b) {
    delta = b.count - a.count;
    pct = a.count ? +((delta / a.count) * 100).toFixed(1) : null;
  }
  return {
    family: hist.family,
    year_a: { year: args.year_a, count: a?.count ?? null },
    year_b: { year: args.year_b, count: b?.count ?? null },
    delta,
    pct_change: pct,
  };
}

export const TOOLS: Anthropic.Tool[] = [
  {
    name: "search_tournaments",
    description:
      "Find tournaments by name, family, or filter. Use this first when the user mentions a tournament by name (e.g. 'Liberty Bell', 'World Open'). Returns up to 20 condensed records with id, current count, point_estimate, and dates.",
    input_schema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Free-text name or partial name to search for." },
        status: { type: "string", enum: ["live", "complete", "historical"], description: "Filter by lifecycle status." },
        year: { type: "integer", description: "Filter by event year." },
        family: { type: "string", description: "Filter by tournament family (substring match)." },
        limit: { type: "integer", minimum: 1, maximum: 50, description: "Max results (default 20)." },
      },
    },
  },
  {
    name: "get_tournament",
    description:
      "Get the full record for a single tournament, including fees, daily_data, historical[], and prior_year_pace. Use this when the user asks for details about ONE tournament. Prefer the id returned by search_tournaments; a name like 'Liberty Bell 2026' also works.",
    input_schema: {
      type: "object",
      properties: {
        id: { type: "string", description: "Tournament id returned by search_tournaments (e.g. 'liberty-bell-2026')." },
        name: { type: "string", description: "Alternative: name like 'Liberty Bell 2026'." },
      },
    },
  },
  {
    name: "top_tournaments",
    description:
      "Get the top N tournaments sorted by a numeric field. Use for 'biggest', 'most entries', 'soonest', 'cheapest', etc.",
    input_schema: {
      type: "object",
      properties: {
        field: {
          type: "string",
          enum: [
            "point_estimate",
            "current_count",
            "ci_upper",
            "ci_lower",
            "days_remaining",
            "early_bird_fee",
            "regular_fee",
            "withdrawal_count",
          ],
          description: "Which numeric field to rank by.",
        },
        n: { type: "integer", minimum: 1, maximum: 20, description: "How many results (default 5)." },
        status: { type: "string", enum: ["live", "complete", "historical"], description: "Filter by lifecycle status." },
        year: { type: "integer", description: "Filter by event year." },
        ascending: { type: "boolean", description: "Sort ascending (smallest first) instead of descending." },
      },
      required: ["field"],
    },
  },
  {
    name: "historical_for_family",
    description:
      "Get the historical entry-count time series for a tournament family. Use for 'show me the trend' or 'how has X done over the years' questions.",
    input_schema: {
      type: "object",
      properties: {
        family: { type: "string", description: "Exact family name (e.g. 'Liberty Bell', 'World Open'). Get from search_tournaments first if uncertain." },
        n_years: { type: "integer", minimum: 1, maximum: 20, description: "Most recent N years (default 5)." },
      },
      required: ["family"],
    },
  },
  {
    name: "compare_years",
    description:
      "Compare entry counts for one tournament family across two specific years. Returns absolute delta and percent change. Use for 'did X grow' or 'is Y up vs last year' questions.",
    input_schema: {
      type: "object",
      properties: {
        family: { type: "string", description: "Exact family name." },
        year_a: { type: "integer", description: "Baseline year." },
        year_b: { type: "integer", description: "Comparison year." },
      },
      required: ["family", "year_a", "year_b"],
    },
  },
];

export function runTool(name: string, input: unknown, data: WebsiteData): unknown {
  const args = (input ?? {}) as Record<string, unknown>;
  switch (name) {
    case "search_tournaments":
      return searchTournaments(data, args as SearchArgs);
    case "get_tournament":
      return getTournament(data, args as { id?: string; name?: string });
    case "top_tournaments":
      return topTournaments(data, args as Parameters<typeof topTournaments>[1]);
    case "historical_for_family":
      return historicalForFamily(data, args as { family?: string; n_years?: number });
    case "compare_years":
      return compareYears(data, args as { family?: string; year_a?: number; year_b?: number });
    default:
      return { error: `Unknown tool: ${name}` };
  }
}

// Compact name-only index. Helps the model know what tournaments EXIST without
// burning a tool call to discover them. Numeric/date fields are stripped so the
// model can't misread them — for actual numbers it must call a tool or use
// code_execution on the mounted JSON.
export function buildIndex(data: WebsiteData): string {
  const rows = data.tournaments
    .map((t) => `${t.family} ${t.year} (${t.status ?? "unknown"})`)
    .sort();
  // Dedup while preserving order.
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const r of rows) {
    if (!seen.has(r)) { seen.add(r); unique.push(r); }
  }
  return unique.join("\n");
}
