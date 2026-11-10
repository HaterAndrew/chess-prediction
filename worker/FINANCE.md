# Tournament receipts

The protected Value column can show expected final receipts recorded in Chess
Action, including memberships and customer fee contributions, after refunds and
before processor fees. Separately collected onsite payments are outside its
coverage. The public attendance model is unchanged.

## Source and authentication

Orders uses `set_player_data_for_datatable.php` for paginated player records,
`invoice.php?oid=…` for independent complete-cart evidence and exact event cash
subtotals, and `ajax_get_txn_total.php` for the financial summary. Excel downloads are useful
for checking source conventions, but repeat order amounts and omit refund
details; they are not the collector's ledger.

A fresh Orders sign-in starts at `/admin/login.php` and submits that form's
`adminlogin` field. `/login.php` is the separate public-account sign-in and
does not establish admin access. The helper follows the verification form's
action only to the approved same-origin login paths. If the admin flow requests
an emailed authentication code, the operator enters it in the terminal.
The scheduled collector therefore
**only reuses an approved session**. It never submits a username/password or
requests another email code. Session expiry is reported as a failed collection;
it does not silently revert to advertised-fee estimates.

Enter credentials and approve a session in an operator-owned terminal:

```sh
python3 tools/finance_credentials.py /private/directory/login.json
python3 tools/finance_login.py /private/directory/login.json /private/directory/session.json
python3 tools/finance_probe.py /private/directory/session.json --tournament 4531
```

Both files must be outside the repository. The helpers create new files with
0600 permissions and never overwrite an existing file. Authentication codes
are entered invisibly. A session helper invocation may send **one** email code;
use the newest email from that invocation. Do not rerun it while its prompt is
waiting. The probe never starts a new login or sends a code.

An approved session's server-side lifetime is not documented or verified.
Daily operation can run without a browser while that session remains valid.
One bounded Orders-page read maintains activity between financial batches.
Money collection runs at minutes 0 and 20; registration training collection
uses minute 40. Session-only reads occupy minutes 10, 30 and 50. Existing daily/weekly eligibility and failed-event
backoff still apply, so a completed fresh collection is not repeated on every tick.
Heartbeats avoid the financial batch's start slot,
write only private session health, and never advance a payment snapshot's source
date. A failed heartbeat marks older projections stale. Periodic activity may
avoid idle expiry; it cannot bypass absolute expiry or an upstream sign-out.
Indefinite operation without reauthorization requires a supported machine feed
or another vendor-supported authentication method. Do not disable two-factor
authentication or automate reading authentication emails to hide expiry.

## Storage and forecasting

`chess-finance` owns a separate private KV namespace and the authenticated
session secret. Its HTTP handler always returns 404, and it has no public route
or preview URL. The public Worker receives only projected figures through the
named `ReceiptService` RPC binding after the Value-key gate. Production finance
bindings are absent from previews; raw source rows are not persisted.

Each financial snapshot reconciles entry money, memberships, contributions,
other fees and refunds with the native summary. Shared-order contributions use
original cash charges and deterministic cent allocation; incomplete invoices,
unknown payment states and ambiguous credits fail the event's collection.
Every positive order requires an independent complete-cart invoice read; matching
selected subtotals alone do not establish cart membership. Invoice event,
section and player-line counts must match the whole-order source rows. Extra
invoice players require a full-order JSON read and a second check against the
same invoice. Exact invoice event subtotals determine event cash and contribution
weights. All rows in an order must share a payment timestamp; allocation within
that event therefore preserves the historical receipt-time bucket. Unknown
invoice layouts, hidden markers and unverified cross-event cash carts fail
visibly. Financial checkpoints use a separate evidence version so older cached
rows cannot bypass these checks. Source payment dates
are explicitly UTC. Recorded Manual cash order totals count as received; the
native fee summary and any cash correction are retained together. Explicit
Manual/Free orders count as zero received even when source face fees and order
totals remain positive; this explicit override has its own
`manual_free_adjustment_cents` provenance. Only complete same-event free orders
without ancillary charges or refunds qualify; mixed or unknown orders fail. Secondary
membership charges require reconciliation before an event can be accepted.
For Approved card orders, forecasts use net charges after verified discounts,
matching the event summary. A one-player invoice can show that net subtotal
while its printed Grand Total and recorded order total remain gross. One
unambiguous signed discount must explain the entire positive gap; the exact
whole cart, source gross components and native net summary must all agree.
Already-net orders are never discounted twice. Raw gross order amounts remain
in the private proof cache alongside a fixed discount variant, verified cents
and the net order basis. Manual cash uses its recorded order total, and explicit
Manual/Free entries contribute zero.
Registration identities are accepted only when a source identifier column
reproduces the public scrape's registration-set hash, or when a unique federation
ID joins source rows to the public registration IDs and reproduces that hash.
When both sides lack federation IDs, a unique exact normalized first/last-name
digest can establish the join. Names and name digests stay in request memory;
snapshots retain only hashed public registration IDs. Ambiguous names and
contradictory federation IDs cannot use this path. Equal row counts do not
establish that match. Legacy scrape records without a hash remain usable for
attendance but cannot authorize a receipts forecast.

Independent count and financial refreshes may occur in either order when the
exact cohort still matches. Both observations must remain fresh and cannot lie
in the future; the financial source timestamp is never advanced by a model refresh.
A source-policy version permits one retry of repaired schema/payment failures
and incomplete old cohort proofs, then restores ordinary daily backoff.

The projection adds receipts expected from remaining advance registrations to
actual net receipts. Receipt yield includes zero-payment registrations and is
measured before cash refunds. A separate remaining-refund reserve prevents
double deduction. Calibration uses two prior family editions, or pooled
completed events when family history is unavailable. Future editions and
pre-split World Open combined financial records are excluded. Historical final
reports cannot establish historical refund timing; use prospective snapshots
for that validation.

Financial batches run at minutes 0 and 20, at most six events per batch.
The separate [registration training feed](REGISTRATIONS.md) uses minute 40.
Active and recently completed events are revisited daily; older calibration
events weekly. Only reconciled snapshots replace existing data. A previous
validated projection may remain visible with an explicit stale marker.
Even-hour batches give calibration first access; odd-hour batches give live
events first access. Costly reports cannot permanently monopolize either
class. Failed events back off until the next UTC day; remaining work
stays due. A batch that reaches its request or overall time limit after saving
new financial checkpoints remains resumable. A report exhausted by requests used
by an earlier event retries with a fresh invocation budget. Checkpoints retain financial fields
only, with no names, contact details, federation IDs or transaction strings.
Fresh target rows must reproduce their exact financial multiset before reuse.
Cross-event cart evidence expires after 24 hours. Complete checkpoints and an
immutable per-generation retirement marker are persisted before history or snapshot
publication. A delayed partial writer cannot erase that marker. KV visibility is
eventually consistent; overlapping attempts may require refetching cached progress.
A reconciliation contradiction involving reused evidence starts one bounded fresh
generation per UTC day and records a separate immutable invalidation marker
before saving the reset. Readers discard that generation even if a delayed writer
restores its root. Fresh evidence that still disagrees remains unavailable.

Each invocation has at most 42 source requests,60 seconds per source request and
8 minutes overall. Target player reports are bounded to8 MB across all pages, with at most
10,000 processed rows. A transaction-filtered cross-event lookup retains every
line of only the requested order IDs, applying the8 MB bound to retained rows;
unrelated broad-query rows are discarded as each page is read. Each report attempt
buffers verified financial proofs into one packed checkpoint, bounded to 8 MB.
Legacy records are read without deletion, at most 128 streamed values per attempt;
streamed legacy bytes plus retained proofs share that envelope. Migrated proofs
keep their original acquisition time and never gain extended pending eligibility.
A partial checkpoint must be saved before an attempt is marked resumable. Reusing
an unchanged pending prefix does not count as new progress. Oversized acquisition fails visibly without
publishing partial results. These envelopes bound supported work; deployment
capacity and daily refresh coverage require live validation. There are 72 bounded
collection opportunities daily; a large event may require several of them, and
complex shared orders can reduce capacity. Check live inventory
and real request costs before promising a daily refresh for every event.

The collector permits at most 12 underlying KV write attempts per financial run,
including failed writes and the outer failure-status path. Reports that cannot fit
their checkpoint, retirement marker, history, snapshot and status writes remain due
for another batch. At the configured 72 financial and 72 session-health runs daily,
the nominal automated ceiling is 936 write attempts. Public Ask and wrong-key
controls, manual runs, duplicate invocations and other namespaces are additional
account usage; this is not an atomic account-wide quota. Existing authorization
and spending limits remain enabled. Current usage already over quota cannot be
recovered until Cloudflare's daily reset.

An open event can have recorded receipts before its registration closing date
is published. Its snapshot keeps that date null; it cannot be used as historical
calibration until a closing date is known. Calendar dates must exist in the UTC
calendar, and payment times cannot overflow into another day. Legacy calendar
failures retry when their required dates are now available; unrelated failures
retain daily backoff. An active-only public identity set is never labeled as
the larger gross registration cohort retained from the index.

Family and pooled calibration caches fail independently, with fixed error logs.
A damaged derived pooled cache is rebuilt from validated family history and a
fresh reconciled source snapshot; other families return as they refresh.

## Validation and rollout

Local validation:

```sh
cd worker
npm ci
npm run typecheck
npm test
npx wrangler deploy --dry-run --config wrangler.finance.toml
npx wrangler deploy --dry-run
```

The native runtime tests compile a local harness into a temporary directory and
exercise the real Worker HTML parser, cookie/redirect handling and HTTP privacy
boundary. All test payments and identities are synthetic. Unit tests do not
prove live source access, real-report accounting, session longevity or accuracy.

Before rollout, validate approved-session reuse from a fresh process, full
pagination and actual report reconciliation for active/completed events,
shared purchases, credits and partial refunds. Compare shadow forecasts with
subsequent source totals. Complete independent security and pipeline review.

`ENTRY_VALUE_MODE = "legacy"` keeps the existing feature working while this
validation is performed. The receipts route never falls back to that formula
once receipts mode is selected. No financial outputs enter the public nightly
data workflow, site assets, Ask input or repository.

Deployment is a separate authorized operation: deploy `wrangler.finance.toml`,
install only `CHESS_ACTION_COOKIE` from the approved private session using the
documented Wrangler secret workflow, deploy the site binding, then set
`ENTRY_VALUE_MODE = "receipts"` after shadow validation. Installing a secret is
itself a deployment. Keep the private snapshot namespace when rolling code
back; switching the explicit mode restores the prior display. The code cannot
restore expired upstream sessions or roll back external payments.
