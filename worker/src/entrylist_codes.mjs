// CCA entry-list URL codes and derivation.
//
// Port of ENTRY_LIST_CODES + _derive_entry_list_code + ENTRY_LIST_URL_TEMPLATE
// from scrape_entries.py (the single source of truth). Kept as plain ESM so
// both the Cloudflare worker (via import) and plain node (the pytest parity
// gate tests/test_entrylist_codes_parity.py) can run it. If you edit the map
// here or in scrape_entries.py, the parity test fails until both match.

export const ENTRY_LIST_CODES = {
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
};

export const ENTRY_LIST_URL_TEMPLATE =
  "https://www.chessaction.com/tournaments/advlists/CCA/" +
  "CCA_{code}{yy}/CCA_{code}{yy}_alp_n.html";

// Mirrors _derive_entry_list_code: strip a leading year, check longer
// patterns first (so "chicago open blitz" beats "chicago open"), fall back
// to initials of significant words.
export function deriveEntryListCode(tournamentName) {
  const nameLower = String(tournamentName || "")
    .replace(/^\d{4}\s+/, "")
    .trim()
    .toLowerCase();
  const patterns = Object.keys(ENTRY_LIST_CODES).sort(
    (a, b) => b.length - a.length
  );
  for (const pattern of patterns) {
    if (nameLower.includes(pattern)) return ENTRY_LIST_CODES[pattern];
  }
  const words = nameLower.match(/[a-z]+/g) || [];
  const skip = new Set(["the", "of", "and", "in", "at", "for", "a", "an"]);
  const code = words
    .filter((w) => !skip.has(w))
    .map((w) => w[0].toUpperCase())
    .join("");
  return code || null;
}

export function entryListUrl(code, year) {
  const yy = String(year).slice(-2);
  return ENTRY_LIST_URL_TEMPLATE.replaceAll("{code}", code).replaceAll(
    "{yy}",
    yy
  );
}
