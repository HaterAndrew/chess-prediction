# Entry-count reconciliation — November 2, 2026

The outcome measure is active plus withdrawn registrations, excluding deleted and rejected rows. The comparison below preserves the original audit snapshots: 30 overlapping 2026 events, 18 exact matches, 12 differences. Export rows include deleted records, so they are not automatically gross-entry outcomes.

| Event (2026) | Export rows | Scrape peak | Difference |
|---|---:|---:|---:|
| Atlantic City Open | 424 | 424 | +0 |
| Atlantic Open | 242 | 242 | +0 |
| Bradley Open | 209 | 209 | +0 |
| Central California Open | 169 | 169 | +0 |
| Chicago Class | 303 | 288 | +15 |
| Chicago Open | 918 | 917 | +1 |
| Chicago Open Blitz | 140 | 134 | +6 |
| Cleveland Open | 179 | 179 | +0 |
| Continental Open | 280 | 266 | +14 |
| DC International | 107 | 107 | +0 |
| DC Open | 188 | 188 | +0 |
| Eastern Chess Congress (in New Jersey) | 447 | 446 | +1 |
| Eastern Class Championships (in Connecticut) | 207 | 196 | +11 |
| Eastern Open | 15 | 15 | +0 |
| Hartford Open | 206 | 206 | +0 |
| Indianapolis Open | 180 | 180 | +0 |
| Kings Island Open | 95 | 95 | +0 |
| Los Angeles Open | 214 | 213 | +1 |
| Midwest Class Championships | 237 | 226 | +11 |
| National Chess Congress | 135 | 135 | +0 |
| New York State Championship | 332 | 332 | +0 |
| New York State Open | 109 | 109 | +0 |
| North American Blitz Championship | 14 | 14 | +0 |
| North American Open | 394 | 394 | +0 |
| Pacific Coast Open | 395 | 394 | +1 |
| Pittsburgh Open | 170 | 170 | +0 |
| Southern Open | 206 | 206 | +0 |
| World Open Under 13 Championship | 86 | 82 | +4 |
| World Open, lower sections | 96 | 93 | +3 |
| World Open, top 6 sections | 1111 | 1066 | +45 |

## Differences

- **2026 Chicago Class:** 14 withdrawals plus a one-entry index/list difference. The public list and admin agree at 289 active + 14 withdrawn; no registration postdates the scrape close. The remaining one-entry cause is not documented.
- **2026 Chicago Open:** One deleted row; current gross is 873 active + 44 withdrawn = 917.
- **2026 Chicago Open Blitz:** Six withdrawn registrations were missing from the scrape gross.
- **2026 Continental Open:** Fourteen withdrawn registrations were missing from the scrape gross.
- **2026 Eastern Chess Congress (in New Jersey):** One deleted row; gross remains 446.
- **2026 Eastern Class Championships (in Connecticut):** Ten withdrawn registrations plus one deleted row. Correct gross is 206.
- **2026 Los Angeles Open:** The Nov 2 export and scrape were taken at different times while entries were open. Latest registration in that export was 00:15:14; a newer scrape already reached 216. This is not a final outcome.
- **2026 Midwest Class Championships:** Eleven withdrawn registrations were missing from the scrape gross.
- **2026 Pacific Coast Open:** One deleted row; gross remains 394.
- **2026 World Open Under 13 Championship:** Four withdrawn registrations were missing because the shared-name lookup skipped World Open groups.
- **2026 World Open, lower sections:** Three withdrawn registrations were missing because the shared-name lookup skipped World Open groups.
- **2026 World Open, top 6 sections:** 44 withdrawals plus a one-entry index/list difference. The event-scoped public list and admin agree at 1,067 active + 44 withdrawn = 1,111; its six section totals sum to 1,111. No registration postdates the scrape close. The remaining one-entry cause is not documented.

## Correction and limits

Eight completed-edition labels are raised using the active/withdrawn aggregates and event-specific public source links in [final_count_corrections.csv](../output/final_count_corrections.csv). Every final registration date is on or before the event end. These are reviewed current outcomes, verified November 2, rather than reconstructed event-day observations. The exact history behind the two one-entry differences remains unavailable; neither is attributed to a new or duplicate registration.

The reconciler validates edition identity, official end date, aggregate counts and evidence dates before writing. New corrections are applied only on or after their verification date and never lower a newer observed peak. This gate does not roll back an already corrected summary. Walk-forward refits use corrected outcomes after event end; they do not reconstruct when revised labels first became available. Original daily scrape rows and registration timestamps are preserved. Future acquisition follows each index card's own entry-list wrapper and generated alphabetical page, checks either active or gross against the index, and retains a warning if no trustworthy page is readable.

This changes data and may change forecasts and outcome grades. It does not tune the estimator or rewrite published prediction values. The prior maintenance report's forecast-equivalence result applies to its earlier chart-only release; this subsequent correction has a different scope.

## Validation

The before/after pipeline comparison changed exactly eight final labels. All 412 current cards retained their point estimates, intervals, routes and tiers. Model source hash remained `e2b539beaa9c6f75`; the stored forecast ledger was unchanged. The sealed cohort retained all 11 records and their point/lower/upper values. Seven grades changed: four Eastern Class horizons (196 → 206) and three Midwest horizons (226 → 237).

The walk-forward retained 1,086 records. Corrected training outcomes changed 33 point estimates and 39 graded finals. T−14 pooled MAE moved from 8.35% to 8.25%; coverage stayed 82.9%. These are retrospective data corrections, not evidence of an estimator improvement. Scrape observations and registration timestamps were not rewritten.
