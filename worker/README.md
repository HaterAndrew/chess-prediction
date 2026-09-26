# chessentries Worker

One Cloudflare Worker serves the site and its API on one origin,
https://chessentries.com. The static site under `docs/` is attached as
Workers Static Assets: every path not listed in `run_worker_first` is answered
by the asset layer directly, with the cache and security headers from
`docs/_headers`. Four paths reach the Worker code: the Ask tab's model proxy,
the health probe, and the two CCA fetch proxies.

## What it does

- `POST /ask` → `{ question, history? }` → returns
  `{ answer, tools_used, latency_ms, cost_usd, model, data_generated }`
- `GET /health` → `{ ok: true, model }`
- `GET /cca-tourlist` (shared secret `CCA_PROXY_KEY`) and
  `GET /cca-entrylist?code=…` (allowlisted codes): the nightly scrape and the
  Audit tab fetch CCA pages through these
- Same-origin requests are admitted on any hostname the Worker answers on
  (the custom domain, the workers.dev fallback, preview URLs); `ALLOWED_ORIGIN`
  lists the extra origins allowed cross-origin, which today is only the static
  dev server
- Rate limit: 20 requests/min per IP and 60/min overall (KV-backed)
- Daily cap: `DAILY_BUDGET_USD` total spend (KV-backed); past the cap `/ask`
  returns 503
- Module-scope data cache, 10-minute TTL, refilled from the Worker's own
  `data/website_data.json` asset through the `ASSETS` binding: no public round
  trip and no stale edge-cache window after the nightly deploy

## Local dev

```sh
cd worker
npm ci
npm run dev                  # serves the whole site + API at http://localhost:8787
```

Node 22 is required (`.mise.toml` at the repo root pins it). Secrets for local
runs go in `worker/.dev.vars` (`ANTHROPIC_API_KEY=…`, `CCA_PROXY_KEY=…`),
which is gitignored. Without a KV namespace the rate-limit and daily-cap
checks short-circuit to "allow"; without `ANTHROPIC_API_KEY`, `/ask` answers
503 with a keyword fallback.

The plain static server (`python3 -m http.server -d docs 8000`) has no API;
the front end points its endpoints at `localhost:8787` when it is served from
any local port other than 8787.

Quick smoke test:

```sh
curl -X POST http://localhost:8787/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "When does Liberty Bell start?"}'
```

## Deploy

Workers Builds deploys on every push to `main`: root directory `worker`, no
build command, deploy command `npx wrangler deploy`, watch paths `worker/*`
and `docs/*`. The nightly data commit therefore redeploys the site by itself.
A manual deploy is `npm run deploy`; `npx wrangler deploy --dry-run` validates
the configuration and the asset manifest without uploading.

Secrets are per Worker and set once from a terminal:

```sh
npx wrangler secret put ANTHROPIC_API_KEY
npx wrangler secret put CCA_PROXY_KEY
```

Preview URLs (`preview_urls = true`) share the production KV namespace and
have no secrets, so `/ask` answers 503 there.

## Tail logs

```sh
npm run tail
```

## Configuration (wrangler.toml)

| Setting | Default | Notes |
|---|---|---|
| `[assets] directory` | `../docs` | The site. `run_worker_first` names the four API paths; everything else never invokes the Worker. |
| `ALLOWED_ORIGIN` | `https://chessentries.com,http://localhost:8080,http://127.0.0.1:8080` | Cross-origin allowlist. Same-origin requests need no entry. |
| `MODEL` | `claude-sonnet-5` | Anthropic model id. Swap to `claude-haiku-4-5` for a large cost reduction. |
| `DAILY_BUDGET_USD` | `1.00` | Hard cap; 503 past this. Charges are recorded one KV key each and summed by prefix, so concurrent turns cannot lose updates. |
| `RATE_LIMIT_PER_MIN` | `20` | Per-IP request cap per 60-second window. |
| `GLOBAL_RATE_LIMIT_PER_MIN` | `60` | Cap across every caller. The per-IP limit alone cannot bind an attacker who rotates through an IPv6 /64 or drives the endpoint from other people's browsers. |

`/ask` requires `Content-Type: application/json` and refuses a request whose
`Origin` header is present, differs from the origin the request arrived on,
and is not on the `ALLOWED_ORIGIN` list. Together those close the cross-site
POST path, which otherwise let any page spend the key without ever reading a
response. A request with no `Origin` at all (curl, the health probe) still
passes and stays covered by the rate limits and the budget.

## Files

- `src/index.ts` — routing only
- `src/agent.ts` — data cache (through `ASSETS`) + the model agent loop
- `src/tools.ts` — 5 tool definitions + handlers operating on the in-memory `WebsiteData`
- `src/prompts.ts` — system prompt template, persona, tournament index injection
- `src/limits.ts` — rate limit, daily budget, price table (fail closed without KV)
- `src/cca-proxy.ts` — tourlist proxy (shared secret) + entry-list proxy (allowlisted codes)
- `src/http.ts` — CORS + JSON responses
