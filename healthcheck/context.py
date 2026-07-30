"""Cross-reference lookups built once from the input CSVs
(data_health, verbatim). Path constants come from shared.paths --
the __file__ derivations would not survive the package move.
"""
import csv
import json
import os
from collections import defaultdict

from tournament_aliases import canonicalize_family

from shared.paths import (METADATA_CSV, PERFORMANCE_JSON, SUMMARY_CSV,
                          UPDATE_LOG_CSV)
from shared.paths import SCRAPE_CSV as DAILY_SCRAPE_CSV


def _canon(name):
    return canonicalize_family(name) if isinstance(name, str) else name


def _strip_year(name):
    if isinstance(name, str) and name.startswith("2026 "):
        return name[5:]
    return name


class Context:
    def __init__(self):
        self.scrape_latest = self._load_scrape_latest()
        self.summary_2026 = self._load_2026_families(SUMMARY_CSV, "tournament_year")
        self.metadata_2026 = self._load_2026_families(METADATA_CSV, "year")
        self.log_hist = self._load_log_history()
        self.perf_finals = self._load_performance_finals()

    def _load_performance_finals(self):
        """canon_family -> {'final_count', 'peak_count_at_T'} from the graded set.

        v3 Q2: data_health never loaded performance_data.json, so the frozen-curve
        corruption behind the wrong-low public grade (T1/R2) had no health or test
        coverage anywhere. Loading it lets the scanner cross-check the numbers the
        grade was computed from against the ones the site publishes.
        """
        out = {}
        if not os.path.exists(PERFORMANCE_JSON):
            return out
        try:
            with open(PERFORMANCE_JSON) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return out
        for t in data.get("tournaments") or []:
            preds = t.get("predictions") or []
            counts = [p.get("count_at_T") for p in preds
                      if isinstance(p.get("count_at_T"), int)]
            out[_canon(t.get("family", ""))] = {
                "final_count": t.get("final_count"),
                "peak_count_at_T": max(counts) if counts else None,
            }
        return out

    def _load_scrape_latest(self):
        """canon_family -> {'net', 'gross', 'date'} from the most recent scrape."""
        latest = {}
        if not os.path.exists(DAILY_SCRAPE_CSV):
            return latest
        with open(DAILY_SCRAPE_CSV, newline="") as fh:
            for row in csv.DictReader(fh):
                fam = _canon(_strip_year(row.get("tournament_name", "")))
                date = row.get("date", "")
                try:
                    entry = int(float(row.get("entry_count") or 0))
                except ValueError:
                    entry = 0
                active_raw = row.get("active_count")
                try:
                    active = int(float(active_raw)) if active_raw not in (None, "") else entry
                except ValueError:
                    active = entry
                net = active if active > 0 else entry
                cur = latest.get(fam)
                if cur is None or date >= cur["date"]:
                    latest[fam] = {"net": net, "gross": entry, "date": date}
        return latest

    def _load_2026_families(self, path, year_col):
        fams = set()
        if not os.path.exists(path):
            return fams
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                yr = str(row.get(year_col, "")).strip()
                if yr.startswith("2026"):
                    fams.add(_canon(row.get("family", "")))
        return fams

    def _load_log_history(self):
        """canon_family -> ordered list of (point_estimate, current_count) for
        live rows, used to detect an estimate frozen while entries rise."""
        hist = defaultdict(list)
        if not os.path.exists(UPDATE_LOG_CSV):
            return hist
        with open(UPDATE_LOG_CSV, newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("status") != "live":
                    continue
                fam = _canon(row.get("family", ""))
                try:
                    pe = int(float(row.get("point_estimate") or 0))
                    cc = int(float(row.get("current_count") or 0))
                except ValueError:
                    continue
                hist[fam].append((pe, cc))
        return hist
