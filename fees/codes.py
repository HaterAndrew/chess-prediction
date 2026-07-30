"""Single home for CCA tournament code tables.

There are TWO code systems plus one probe heuristic — they are related but
NOT projections of one table, and this file deliberately keeps them separate
rather than inventing a false unification:

- FAMILY_TO_CODE: family display name -> chesstour.com FLYER code (the
  <code><yy>.htm page that carries the fee schedule). Owner of record for
  merge_fees' fee fill and the tests' data<->code parity gate.
- ENTRY_LIST_CODES: lowercase scraped tournament name (including spelling
  variants) -> chessaction.com ENTRY-LIST code (uppercase; a different
  namespace: Chicago Open is "chio" on chesstour but "CHI" on chessaction).
  Mirrored in worker/src/entrylist_codes.mjs; tests/test_entrylist_codes_parity
  keeps Python and JS in lockstep.
- FLYER_PROBE_CODES: blind-discovery probe list scrape_fees tries against
  chesstour URLs when chessevents discovery comes up empty. A heuristic, not
  a mapping — changing it changes network behavior, so it moved here verbatim.

Before the 2026-07-30 decomposition these lived in validate_fees.py,
scrape_entries.py, and scrape_fees.py respectively and drifted independently
(audit v5 "fee-table unification"). The legacy module attributes still exist
(re-imports), so monkeypatching call sites keep working.
"""

# family display name -> chesstour flyer code.
FAMILY_TO_CODE = {
    "Atlantic City Open": "aco",
    "Atlantic Open": "ao",
    "Bradley Open": "brad",
    "Central California Open": "cco",
    "Chicago Open": "chio",
    "Cleveland Open": "clev",
    "Continental Open": "cono",
    "Indianapolis Open": "io",
    "Kings Island Open": "kio",
    "Los Angeles Open": "lao",
    "Midwest Class Championships": "mwcc",
    "New York State Championship": "nysc",
    "Pittsburgh Open": "pit",
    "Pacific Coast Open": "pco",
    "National Chess Congress": "ncc",
    "Liberty Bell Open": "lbo",
    "Golden State Open": "gso",
    "Mid-America Open": "mao",
    "Chicago Class": "chcc",
    "Southern Class": "scc",
    "World Open": "wo",
    "World Open top 6 sections": "wo",
    "North American Open": "nao",
    "Boston Chess Congress": "bcc",
    # v5 Cat F: the 2026 flyers say ecc = Eastern CLASS (Oct 16), ecco =
    # Eastern Chess CONGRESS (Oct 23). The old "Eastern Chess Congress: ecc"
    # pairing failed merge_fees' +/-3-day date cross-check every week —
    # silently, because the unmapped/mismatched skip carried no warning.
    "Eastern Class Championships": "ecc",
    "Eastern Chess Congress": "ecco",
    # v5 follow-up: eo verified from the eo22/eo23/eo24 flyer URLs already in
    # tournament_fees.csv; naob follows the side-event blitz convention
    # (aob/conob/eccob/...). Neither 2026 flyer is published yet — the mapping
    # waits for it, and the +/-3-day date cross-check guards a wrong guess.
    "Eastern Open": "eo",
    "North American Blitz Championship": "naob",
    "Continental Class": "ccc",
    "Hartford Open": "ho",
    "New York State Open": "nyso",
    "DC International": "dci",
    "DC Open": "dco",
    "World Open lower sections": "wolower",
    "World Open Under 13 Championship": "wu",
}

# Flyer codes that exist on chesstour.com but deliberately map to no family:
# blitz side events sharing the parent flyer's code with a "b" suffix carry
# no advance fee schedule. The parity test in tests/test_scrape_fees.py
# fails when a scraped code is neither mapped above nor listed here, so a
# newly discovered flyer cannot fall through silently (v5 Cat F).
UNMAPPED_CODES = {
    "aob", "conob", "eccob", "kiob", "laob", "mwccb", "pcob",
}

# Blind-discovery probe list (moved verbatim from scrape_fees.TOURNAMENT_CODES).
# KNOWN DISCREPANCIES vs FAMILY_TO_CODE, recorded not fixed (changing the list
# changes which URLs get probed — a behavior decision, parked in the ledger):
#   "lib"  — FAMILY_TO_CODE says Liberty Bell Open = "lbo"
#   "scc"  — annotated "Southern California Chess" upstream; the authoritative
#            mapping says scc = Southern Class
#   "cco"  — annotated "Cherry Blossom / Continental Chess"; authoritative
#            mapping says cco = Central California Open
#   "pho", "uso", "lvo", "dc" — probe-only codes with no mapped family
FLYER_PROBE_CODES = [
    "wo", "chio", "nao", "lib", "ncc", "aco", "scc",
    "pho", "uso", "eo", "ao", "lvo", "cco", "dc",
]

# lowercase scraped tournament name (incl. spelling variants) ->
# chessaction.com entry-list code. Mirror: worker/src/entrylist_codes.mjs.
ENTRY_LIST_CODES = {
    "atlantic city open": "ACO",
    "atlantic open": "AO",
    "world open": "WO",
    "chicago open blitz": "COB",
    "chicago open": "CHI",
    "chicago class": "CC",
    "liberty bell open": "LBO",
    "george washington open": "GWO",
    "golden state open": "GSO",
    "pacific coast open": "PCO",
    "pittsburgh open": "PIT",
    "cleveland open": "CLEV",
    "bradley open": "BRAD",
    "dc international": "DCI",
    "dc open": "DCO",
    "hartford open": "HO",
    "new york state championship": "NYSC",
    "new york state open": "NYSO",
    "southern open": "SO",
    "central california open": "CCO",
    "national chess congress": "NCC",
    "north american open": "NAO",
    "eastern open": "EO",
    "los angeles open": "LAO",
    "mid-america open": "MAO",
    "mid america open": "MAO",
    "new york open": "NYO",
    "kings island open": "KIO",
    "eastern chess congress": "ECC",
    "western class": "WC",
    "national open": "NO",
    "las vegas open": "LVO",
    "southwest class": "SWC",
    "boston chess congress": "BCC",
}
