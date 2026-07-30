"""Compatibility shim -- implementation lives in scrapers/entries.py
(2026-07-30 decomposition). The filename is load-bearing: pipeline.steps
runs it by name and the worker parity test pins the legacy surface.
"""

from scrapers.entries import (  # noqa: F401
    ENTRY_LIST_CODES,
    ENTRY_LIST_URL_TEMPLATE,
    TODAY,
    _derive_entry_list_code,
    _parse_index,
    consolidate_world_open,
    main,
    run_scrape_pipeline,
    scrape_index,
    to_family,
)

if __name__ == "__main__":
    main()
