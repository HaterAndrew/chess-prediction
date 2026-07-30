# Date verification sweep, 2021-2025 (issues #5, #6, #7)

Run 2026-07-30 with `tools/verify_dates.py --year <y> --verbose`. Metadata has
no rows before 2021, so 2021 is the entire pre-2022 surface (2019/2020 return
"no metadata rows for this year"). After expanding the slug map (issue #6) the
sweep was repeated for every past year. Post-repair totals: 2021 verified=9,
2022 verified=24, 2023 verified=27, 2024 verified=30, 2025 verified=32, all
with drift>1d=0.

## Results for mapped families (9 verified)

| Family | Metadata | Canonical | Outcome |
|---|---|---|---|
| Atlantic Open | 2021-08-26 | 2021-08-27 | OK (1-day convention slack) |
| Central California Open | 2021-08-18 | 2021-08-20 | REPAIRED to 2021-08-20 / end 2021-08-22 |
| Continental Open | 2021-08-12 | 2021-08-12 | OK (drift 0) |
| Eastern Chess Congress | 2021-09-30 | 2021-10-01 | OK |
| Indianapolis Open | 2021-08-25 | 2021-08-27 | REPAIRED to 2021-08-27 / end 2021-08-29 |
| Kings Island Open | 2021-11-11 | 2021-11-12 | OK |
| Los Angeles Open | 2021-11-04 | 2021-11-05 | OK |
| Midwest Class Championships | 2021-10-07 | 2021-10-08 | OK |
| New York State Championship | 2021-09-03 | 2021-09-03 | OK (drift 0) |

Repair source: `chessevents.com/event/centralcalifornia/2021` and
`/event/indianapolis/2021`, full start and end spans parsed by the tool's own
`parse_chessevents_dates`. Both repaired editions land on the Friday-Sunday
pattern every later year of each family follows.

## Drifts caught by the expanded map (repaired the same day)

The new Niagara Falls Open mapping immediately surfaced two more drifted rows,
both repaired from `chessevents.com/event/niagarafalls/<year>`:

| Edition | Metadata was | Canonical |
|---|---|---|
| Niagara Falls Open 2024 | 2024-05-29 to 2024-06-01 | 2024-05-31 to 2024-06-02 |
| Niagara Falls Open 2025 | 2025-04-30 to 2025-05-03 | 2025-05-02 to 2025-05-04 |

Remaining source-parse gaps, left annotated only: the `niagarafalls/2021`
page and the `princeton/2022`, `/2023`, and `/2024` pages exist but carry no
dates (placeholder pages — chessevents only has Princeton Open content for
2025), so those editions stay unverified with no canonical source located.

## Issue #7: Continental Open 2021 low scrape coverage

Date verified drift 0, so the 0.40 ratio is not a date-truncation bug. The
edition is covid-flagged and excluded from both ratio engines. Root cause is
COVID-era sparse registration-timestamp coverage; the ratio can never improve.
Allowlisted in `dataprep/reporting.py` (`_known_low_coverage`) so the nightly
warning payload drops the permanent entry while the guardrail keeps firing for
new editions.

## Issue #6: unmapped-family audit

Classified every metadata family absent from both verifier maps by its most
recent year:

- 11 active main-event families now mapped in `CHESSEVENTS_SLUGS`, each slug
  confirmed by fetching the page and matching its title: Boston Chess
  Congress, Eastern Open, George Washington Open, Golden State Open, Liberty
  Bell Open, Mid-America Open, Niagara Falls Open, Southern Class
  Championships, Southwest Class Championships, Western Class Championships,
  and Atlantic City Open via the `princeton` slug (FAMILY_GROUPS folds
  Princeton Open into that lineage; its pre-2026 editions ran under the old
  name).
- Atlantic City Open 2026 has no chessevents page yet and chesstour's current
  listing no longer carries the spring 2026 edition: no canonical source
  located for that single edition.
- Festival sub-events (World Open G/7, G/10, G/50, Blitz, Action, Amateur,
  Senior Amateur, Womens; George Washington Saturday/Sunday Octos; Chicago
  Open Blitz; North American Blitz) have no standalone canonical pages;
  chessevents lumps the festival. Left unmapped by design.
- NY State scholastic/junior/senior side events: no canonical source located.
- 74 dead lineages (last year 2024 or earlier, mostly monthly ICC-era opens
  and Action events) left in metadata untouched; nothing live depends on
  them.

Data-hygiene finding, not fixed here: the metadata contains spelling-duplicate
sub-event families (World Open G/7 vs G7, G/10 vs G 10, G/50 vs G 50) that
`extract_family` treats as distinct. Owner call whether to merge them via
FAMILY_GROUPS.
