// CCA fetch proxies + the shared-secret comparison (index.ts, verbatim; W1).
// @ts-expect-error plain ESM shared with node (pytest parity gate); no types.
import { deriveEntryListCode, entryListUrl } from "./entrylist_codes.mjs";

import type { Env } from "./env";
import { jsonResponse, pickAllowedOrigin } from "./http";
import { checkRateLimit } from "./limits";

// ── CCA tournament-list fetch proxy ────────────────────────────────────────
// chessaction.com started 403-blocking GitHub Actions' Azure IP ranges, which
// breaks the daily scraper in CI (a residential IP and Cloudflare's edge both
// still get 200). This route lets the GH Action fetch the tournament list
// THROUGH Cloudflare's edge instead of hitting the site directly. It replays
// the exact AJAX POST the scraper would have made and returns the upstream
// bytes verbatim, so the Python parser is unchanged. Gated by a shared secret
// (X-Proxy-Key) so it isn't an open proxy.
const CCA_TOURLIST_URL = "https://www.chessaction.com/ajaxFrontGetTourListNew.php";
const CCA_VENDOR_ID = "3";

/**
 * Constant-time string comparison (v3 S6).
 *
 * `!==` on a secret returns as soon as it hits a differing byte, so response
 * time leaks how many leading characters were correct and the key can be
 * recovered a character at a time. The XOR-accumulate form always walks the
 * full length. Comparing lengths first would reintroduce a leak, so the length
 * difference is folded into the accumulator instead.
 */
export function timingSafeEqual(a: string, b: string): boolean {
  const len = Math.max(a.length, b.length);
  let diff = a.length ^ b.length;
  for (let i = 0; i < len; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}

export async function proxyCcaTourList(env: Env, request: Request): Promise<Response> {
  const expected = env.CCA_PROXY_KEY;
  const provided = request.headers.get("X-Proxy-Key");
  // Require the secret to be configured AND matched. Fail closed.
  if (!expected || !provided || !timingSafeEqual(provided, expected)) {
    return new Response("Forbidden", { status: 403 });
  }

  try {
    const upstream = await fetch(CCA_TOURLIST_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent":
          "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        Accept: "text/html,*/*",
        Referer: "https://www.chessaction.com/",
      },
      body: `vendor_search=${CCA_VENDOR_ID}&length=-1`,
    });

    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        // Surface the upstream status to the caller for diagnostics.
        "X-Upstream-Status": String(upstream.status),
      },
    });
  } catch (e) {
    return new Response(`Upstream fetch failed: ${(e as Error).message}`, { status: 502 });
  }
}

// Browser-facing proxy for CCA public entry-list pages. The PWA's Audit tab
// cannot fetch chessaction.com directly (CSP connect-src + no CORS upstream),
// so it asks this route for the page. Unlike /cca-tourlist this is meant for
// the browser: CORS headers via pickAllowedOrigin, per-IP rate limiting, and
// no shared secret — the URL space is a strict template over an allowlisted
// event-name map (entrylist_codes.mjs), not an open proxy.
export async function proxyCcaEntryList(env: Env, request: Request): Promise<Response> {
  const url = new URL(request.url);
  const event = url.searchParams.get("event") ?? "";
  const year = url.searchParams.get("year") ?? "";

  if (!/^20(2\d|3[0-5])$/.test(year)) {
    return jsonResponse({ error: "bad_year", message: "year must be 2020-2035" }, { status: 400 }, env, request);
  }
  const code = deriveEntryListCode(event);
  if (!code || !/^[A-Z]{1,6}$/.test(code)) {
    return jsonResponse({ error: "unknown_event", message: `cannot derive an entry-list code from "${event}"` }, { status: 400 }, env, request);
  }

  const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
  const rl = await checkRateLimit(env, ip);
  if (!rl.ok) {
    return jsonResponse(
      { error: "rate_limited", message: "Too many requests — wait a minute." },
      { status: 429, headers: { "Retry-After": String(rl.retryAfter ?? 60) } },
      env,
      request
    );
  }

  try {
    const upstream = await fetch(entryListUrl(code, year), {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        Accept: "text/html,*/*",
        Referer: "https://www.chessaction.com/",
      },
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "Access-Control-Allow-Origin": pickAllowedOrigin(env, request),
        // Custom headers are invisible to cross-origin JS unless exposed.
        "Access-Control-Expose-Headers": "X-Entry-Code, X-Upstream-Status",
        Vary: "Origin",
        "X-Entry-Code": `CCA_${code}${year.slice(-2)}`,
        "X-Upstream-Status": String(upstream.status),
      },
    });
  } catch (e) {
    return jsonResponse(
      { error: "upstream_failed", message: (e as Error).message },
      { status: 502 },
      env,
      request
    );
  }
}
