"""Cross-reference lookups built once from the input CSVs
(data_health, verbatim). Path constants come from shared.paths --
the __file__ derivations would not survive the package move.
"""
import csv
import json
import os
from collections import defaultdict, namedtuple

from tournament_aliases import canonicalize_family, cca_family

from shared.editions import split_edition_name
from shared.paths import (METADATA_CSV, PERFORMANCE_JSON, SUMMARY_CSV,
                          UPDATE_LOG_CSV)
from shared.paths import SCRAPE_CSV as DAILY_SCRAPE_CSV


def _canon(name):
    return canonicalize_family(name) if isinstance(name, str) else name


# One logged run of one card. prediction_source names the estimator that
# produced the row, so the freeze check can tell an interim metadata mean
# (expected to sit still) from model output (expected to move nightly).
LogRun = namedtuple("LogRun", "point_estimate current_count prediction_source")


def _run_year(row):
    """The edition year of one logged run.

    Rows written before the `year` column existed carry none. The writer logged
    current-season cards only back then, so the run's own year is the edition's.
    """
    raw = (row.get("year") or "").strip()
    if raw:
        return int(float(raw))
    stamp = row.get("run_timestamp") or ""
    return int(stamp[:4]) if stamp[:4].isdigit() else None


def load_log_history(path=None):
    """(canon_family, year) -> ordered list of LogRun for live rows, used to
    detect an estimate frozen while entries rise.

    Keyed on the edition so next season's card, open while this season's card
    of the same family is still in the 90-day log, reads only its own runs.

    Runs logged before update_log.csv carried prediction_source read as None:
    unattributable, and counted toward no card's freeze window.
    """
    hist = defaultdict(list)
    path = path or UPDATE_LOG_CSV
    if not os.path.exists(path):
        return hist
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("status") != "live":
                continue
            try:
                pe = int(float(row.get("point_estimate") or 0))
                cc = int(float(row.get("current_count") or 0))
            except ValueError:
                continue
            try:
                year = _run_year(row)
            except ValueError:
                continue
            hist[(_canon(row.get("family", "")), year)].append(
                LogRun(pe, cc, row.get("prediction_source") or None))
    return hist


def load_last_run_timestamp(path=None):
    """run_timestamp of the newest run in update_log.csv, or None.

    step_log_run writes the run's RUN_TS, the same value stamped into
    website_data.json as last_updated, so the freeze check can tell whether
    tonight's run is already in the log.
    """
    path = path or UPDATE_LOG_CSV
    if not os.path.exists(path):
        return None
    with open(path, newline="") as fh:
        stamps = [row.get("run_timestamp") for row in csv.DictReader(fh)]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else None


def _strip_year(name):
    family, _year = split_edition_name(name)
    return family if family is not None else name


def _scrape_edition(row):
    """(canon_family, year) of one daily_scrape.csv row. A name with no year
    prefix takes the year it was scraped in."""
    name = row.get("tournament_name", "")
    family, year = cca_family(name), split_edition_name(name)[1]
    if year is None:
        date = row.get("date", "")
        year = int(date[:4]) if date[:4].isdigit() else None
    return _canon(family), year


class Context:
    def __init__(self):
        self.scrape_latest = self._load_scrape_latest()
        self.summary_2026 = self._load_2026_families(SUMMARY_CSV, "tournament_year")
        self.metadata_2026 = self._load_2026_families(METADATA_CSV, "year")
        self.log_hist = self._load_log_history()
        self.last_logged_run = load_last_run_timestamp(UPDATE_LOG_CSV)
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
        """(canon_family, year) -> {'net', 'gross', 'date'} from the most recent
        scrape of each edition."""
        latest = {}
        if not os.path.exists(DAILY_SCRAPE_CSV):
            return latest
        with open(DAILY_SCRAPE_CSV, newline="") as fh:
            for row in csv.DictReader(fh):
                fam = _scrape_edition(row)
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
        return load_log_history(UPDATE_LOG_CSV)
