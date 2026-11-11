import { ChessActionClient } from "../src/finance/client";
import { collectBatch } from "../src/finance/collect";
import { receiptForecast } from "../src/finance/forecast";
import { cohortHash, sha256, snapshotKey, type ReceiptCard, type ReceiptSnapshot } from "../src/finance/types";

/** Observe first source access under a budget that only permits one attempt. */
export async function recoveryPriority(request: Request): Promise<Response> {
  const { kind = "missing", healthyAgeHours = 7, calibration = false, now = "2026-11-09T03:00:00Z" } = await request.json() as {
    kind?: string; healthyAgeHours?: number; calibration?: boolean; now?: string };
  const tick = Date.parse(now);
  const healthyAt = new Date(tick - healthyAgeHours * 3_600_000).toISOString();
  const recoveryAt = "2026-11-08T23:00:00.000Z";
  const store = new Map<string, string>();
  const kv = { get: async (key: string | string[]) => Array.isArray(key) ? new Map(key.map(k => [k,store.get(k) ?? null])) : store.get(key) ?? null,
    put: async (key: string, value: string) => { store.set(key,value); } } as unknown as KVNamespace;
  const cards: ReceiptCard[] = ["Healthy Open", "Recovery Open"].map(family => ({family,year:2026,status:"live",current_count:0,
    point_estimate:5,regular_fee:10,event_start:"2026-11-14",count_observed_at:"2026-11-09T00:00:00.000Z"}));
  for (const card of cards) card.count_cohort_hash = await cohortHash([]);
  const snapshot = (card: ReceiptCard, id: string, asOf: string): ReceiptSnapshot => ({schema:1,family:card.family,year:2026,tournament_id:id,
    source_as_of:asOf,event_start:"2026-11-14",registration_close:null,regular_fee_cents:1000,registration_count:0,
    summary:{entry_cents:0,membership_cents:0,contribution_cents:0,other_cents:0,refunded_cents:0,net_cents:0},
    cohort:[],buckets:[],previous_net_cents:null,previous_as_of:null});
  const healthy = snapshot(cards[0],"1",healthyAt);
  const history: ReceiptSnapshot = {...healthy,year:2025,tournament_id:"10",event_start:"2025-11-14",registration_close:"2025-11-14",
    source_as_of:"2025-11-15T00:00:00.000Z",registration_count:1,summary:{...healthy.summary,entry_cents:1000,net_cents:1000},
    cohort:[{id:await sha256("1"),paid_at:"2025-11-14T00:00:00.000Z"}],
    buckets:[{days_before:0,registrations:1,entry_cents:1000,membership_cents:0,contribution_cents:0,other_cents:0}]};
  store.set("history:Healthy%20Open",JSON.stringify([history]));
  store.set(snapshotKey(cards[0].family,2026),JSON.stringify({...healthy,source_policy_version:3}));
  store.set("event_status:Healthy%20Open:2026",JSON.stringify({attempted_at:healthyAt,ok:true,reason:null,source_policy_version:3}));
  if (kind !== "missing") {
    const prior = snapshot(cards[1],"2",recoveryAt);
    if (kind === "cohort") {
      cards[1].current_count=1;cards[1].count_cohort_hash=await cohortHash([await sha256("10")]);
      prior.registration_count=1;
      prior.buckets=[{days_before:13,registrations:1,entry_cents:0,membership_cents:0,contribution_cents:0,other_cents:0}];
    }
    store.set(snapshotKey(cards[1].family,2026),JSON.stringify({...prior,source_policy_version:kind === "cohort" ? 2 : 3}));
  }
  store.set("event_status:Recovery%20Open:2026",JSON.stringify({attempted_at:kind === "resume" || kind === "blocked" ? "2026-11-09T02:20:00.000Z" : recoveryAt,
    ok:kind === "healthy" || kind === "cohort",reason:kind === "healthy" || kind === "cohort" ? null : kind === "blocked" ? "source_login_expired" : "source_request_limit",
    resume:kind === "missing" || kind === "resume",source_policy_version:kind === "cohort" ? 2 : 3}));
  if (calibration) cards.push({family:"Finished Open",year:2026,status:"complete",current_count:0,event_start:"2026-11-01",event_end:"2026-11-02"});
  const source = new ChessActionClient();
  source.resume = async () => `<select id="tournments">${cards.map((card,i)=>`<option value="${i+1}">2026 ${card.family}</option>`).join("")}</select>`;
  const attempted: string[]=[];
  source.request = async (_path, fields) => {attempted.push(fields!.tname);throw Error("source_request_limit");};
  const result = await collectBatch({FINANCE_KV:kv,CHESS_ACTION_COOKIE:"synthetic"},cards,tick,source);
  return Response.json({attempted,result,healthyMissing:(await receiptForecast(cards[0],healthy,[history],tick)).missing});
}
