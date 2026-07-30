// Worker environment bindings + request shapes (split from index.ts,
// 2026-07-30 decomposition W1).

export interface Env {
  ANTHROPIC_API_KEY: string;
  ALLOWED_ORIGIN: string;
  DATA_URL: string;
  MODEL: string;
  DAILY_BUDGET_USD: string;
  RATE_LIMIT_PER_MIN: string;
  KV?: KVNamespace;
  // Shared secret gating the /cca-tourlist scrape proxy (see proxyCcaTourList).
  CCA_PROXY_KEY?: string;
}

export interface AskRequest {
  question: string;
  history?: Array<{ role: "user" | "assistant"; content: string }>;
}
