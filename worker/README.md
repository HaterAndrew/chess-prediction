# chess-ask Worker

Cloudflare Worker that proxies the Chess Entry Predictor's "Ask" tab to the
Anthropic API. Holds the API key as a secret, answers tournament questions
over a 5-tool function-calling loop against a live snapshot of
`website_data.json` from GitHub Pages.

## What it does

- `POST /ask` → `{ question, history? }` → returns
  `{ answer, tools_used, latency_ms, cost_usd, model, data_generated }`
- `GET /health` → `{ ok: true, model }`
- CORS-locked to `ALLOWED_ORIGIN` (default `https://haterandrew.github.io`)
- Rate-limit: 20 requests/min per IP (KV-backed)
- Daily cap: $2.00/day total spend (KV-backed); past cap returns 503
- Module-scope data cache, 10-minute TTL, refetched from `DATA_URL` on miss

## Local dev

```sh
cd worker
npm install
npx wrangler login            # one time
npx wrangler kv:namespace create CHESS_ASK_KV     # for rate-limit + cost cap
# Paste the returned id into wrangler.toml under [[kv_namespaces]]
npx wrangler secret put ANTHROPIC_API_KEY          # paste your key
npm run dev                                        # starts on localhost:8787
```

Quick smoke test:

```sh
curl -X POST http://localhost:8787/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "When does Liberty Bell start?"}'
```

For local dev **without** a deployed KV namespace, the rate-limit and
daily-cap checks short-circuit to "allow" (they're guarded by `if (env.KV)`).
You still need `ANTHROPIC_API_KEY` set.

## Deploy

```sh
npm run deploy
```

After deploy, paste the assigned URL (e.g.
`https://chess-ask.<account>.workers.dev/ask`) into the frontend's
`ASK_ENDPOINT` constant.

## Tail logs

```sh
npm run tail
```

## Configuration (wrangler.toml `[vars]`)

| Var | Default | Notes |
|---|---|---|
| `ALLOWED_ORIGIN` | `https://haterandrew.github.io` | CORS origin. Set to `http://localhost:8080` (or whatever the frontend uses) for local dev. |
| `DATA_URL` | `https://haterandrew.github.io/chess-prediction/website_data.json` | Where to fetch tournament data. |
| `MODEL` | `claude-sonnet-4-6` | Anthropic model id. Swap to `claude-haiku-4-5` for ~5× cost reduction. |
| `DAILY_BUDGET_USD` | `2.00` | Hard cap; 503 past this. |
| `RATE_LIMIT_PER_MIN` | `20` | Per-IP request cap per 60-second window. |

## Files

- `src/index.ts` — request handler, CORS, rate-limit, tool-call loop, cost tracking
- `src/tools.ts` — 5 tool definitions + handlers operating on the in-memory `WebsiteData`
- `src/prompts.ts` — system prompt template, persona, tournament index injection
