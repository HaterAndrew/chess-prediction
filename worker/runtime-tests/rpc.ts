// Synthetic local assets; the public routing and private RPC implementations are real.
import publicWorker from "../src/index";
import type { Env } from "../src/env";

export default {
  fetch(request: Request, env: Env & { TEST_DATA: unknown }, ctx: ExecutionContext) {
    return publicWorker.fetch(request, { ...env,
      ASSETS: { fetch: async () => Response.json(env.TEST_DATA) } as unknown as Fetcher,
    }, ctx);
  },
};
