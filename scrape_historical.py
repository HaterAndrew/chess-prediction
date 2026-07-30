"""Compatibility shim -- implementation lives in scrapers/historical.py
(2026-07-30 decomposition). The filename is load-bearing:
run_enrichment.SCRAPERS and the weekly workflow run it by name.
"""

from scrapers.historical import (  # noqa: F401
    derive_tournament_code,
    extract_year,
    main,
    normalize_date,
    parse_entry_list_html,
    parse_tournament_record,
)

if __name__ == "__main__":
    main()
