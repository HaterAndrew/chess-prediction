"""Compatibility shim -- implementation lives in scrapers/standings.py
(2026-07-30 decomposition). The filename is load-bearing:
run_enrichment.SCRAPERS and the weekly workflow run it by name.
"""

from scrapers.standings import scrape_all  # noqa: F401

if __name__ == "__main__":
    scrape_all()
