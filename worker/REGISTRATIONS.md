# Registration training feed

The private collector reads active and withdrawn registrations from Chess
Action’s registration table. It publishes aggregate counts, registration-date
extrema and daily histograms. Names, contact details, federation IDs, order
records and the admin session stay outside the feed and the public repository.

`createdAt` contains the local registration time displayed by the admin page.
That display matches the existing export’s `registered_time`; the similarly
named `created_at` database field differs. The page’s GMT label disagrees with
its UTC title by one hour on some historical rows, so the collector keeps the
verified local display and does not convert it using that label.

A report includes active and withdrawn entries, matching the export’s gross
registration count. Tournament IDs must match every row, registration IDs must
be unique across both scopes, pagination must be complete, and final count
checks must agree. These checks detect count changes during collection; they
cannot establish an atomic snapshot of a source without a revision token.
Unknown layouts, invalid dates and mismatched editions fail collection.

The collector stores two count histograms: exact whole-day offsets from the
latest registration, and calendar-date counts. The first reproduces
`floor((last_reg - registered_time) / 86400)` used by the existing corpus. No
per-registration timestamp list or player identifier is stored.

Collection at minute 40 runs independently of financial reconciliation, with
one historical and two live reports per opportunity when both queues are due.
Live reports refresh daily; completed reports refresh weekly. Failed reports
back off until the next UTC day, except a report deferred after earlier work
exhausted the invocation’s request budget. Last-good aggregates remain stored.
Training status cannot mark a valid financial projection stale.

Money collection occupies minutes 0 and 20; session heartbeats remain at
minutes 10, 30 and 50. Every collection opportunity shares the existing cap of
12 attempted KV writes, including failed writes and diagnostic writes. The
configured schedule therefore has a nominal ceiling of 936 writes per day.
Duplicate deliveries, manual operations and other account traffic remain
outside that nominal calculation.

The public Worker exposes `GET /registration-feed` through the private
`ReceiptService` binding. It requires the existing CI `X-Proxy-Key`, loads its
own event cards and accepts no caller-selected source URL or tournament ID.
Reads perform no KV writes. Preview environments have neither the key nor the
private binding. Responses use `Cache-Control: no-store`, contain at most 200
eligible editions and are capped at 6 MB; individual cache records are bounded.

The nightly prediction step uses the existing `CCA_PROXY_URL` and
`CCA_PROXY_KEY` configuration. Python validates the complete aggregate envelope
before merging it into `tournament_summary.csv` and
`daily_registration_counts.csv`. A local collection can supply the same
aggregate envelope through `REGISTRATION_FEED_PATH`.

Existing timestamped manual curves and corpus IDs are retained. A collected
edition receives source provenance and remains refreshable; its observed
scrape peak is never reduced. Source IDs are separate from corpus IDs and must
remain consistent on later imports. A failed or stale report preserves its
previous curve and surfaces a warning. Zero-entry events wait for registrations.
Training imports require a report captured after the event’s final calendar
day, with a 14-hour timezone margin. A report collected during an event remains
private until a final capture is available. Newly completed events receive a
final capture before the usual weekly refresh deadline. Live cards keep their
public scrape history, so newer admin registrations cannot outrun the chart’s
observed public count. The feed does not rebuild the archive from a partial
export or rebase its exact histogram to a scrape date. The estimator’s
numerical rules and original forecast records are unchanged.

The feed reuses the approved admin session and its existing heartbeat. It does
not start a password login or request an email code. Absolute session expiry
still requires operator reauthorization, as described in [FINANCE.md](FINANCE.md).
