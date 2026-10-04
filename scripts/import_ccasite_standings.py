"""Rebuild historical_standings rows from cca-site's standings, into a scratch
directory, with an agreement report against the committed rows.

    .venv/bin/python scripts/import_ccasite_standings.py --out <dir> [--cca-site ../cca-site]

Writes <dir>/historical_standings.csv and <dir>/agreement.md. It never
writes under output/: the rebuilt file replaces the committed one only in
its own reviewed change. Counts and section names only; no player names or
IDs leave cca-site.
"""
import argparse
import csv
import io
import os
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.paths import OUTPUT_DIR, PROJECT_DIR  # noqa: E402
from standings.agreement import (against_final_counts, compare, render,  # noqa: E402
                                 render_final_counts)
from standings.ccasite import read_editions, read_events  # noqa: E402
from standings.families import Folder, folder_spellings, legacy_standings_name  # noqa: E402
from standings.importer import build_rows  # noqa: E402
from standings.output_files import (STANDINGS_CSV, final_counts, read_standings,  # noqa: E402
                                    spelling_years, write_standings)
from tournament_aliases import canonicalize_family  # noqa: E402

YEAR_BANDS = ((0, 2008, "before 2009"), (2009, 2012, "2009-2012"), (2013, 9999, "2013 on"))


def _committed_rows(ref=None):
    if ref is None:
        return read_standings(os.path.join(OUTPUT_DIR, STANDINGS_CSV))
    text = subprocess.run(["git", "-C", PROJECT_DIR, "show", f"{ref}:output/{STANDINGS_CSV}"],
                          check=True, capture_output=True, text=True, encoding="utf-8").stdout
    return list(csv.DictReader(io.StringIO(text)))


def _summary_lines(report):
    bands = Counter(label for row in report.rows for lo, hi, label in YEAR_BANDS
                    if lo <= row["year"] <= hi)
    lines = ["# cca-site standings import", "",
             f"{len(report.rows)} rows: " + ", ".join(f"{bands[b[2]]} {b[2]}" for b in YEAR_BANDS) + ".",
             f"{sum(report.untracked.values())} editions in {len(report.untracked)} folders "
             "outside the tracked families, not imported.",
             f"{report.without_standings} editions with no standings files.", "",
             "Sections dropped: " + ", ".join(f"{n} {reason}" for reason, n in report.dropped.most_common()) + ".",
             "", "## Findings", ""]
    return lines + [f"- {note}" for note in report.notes] + [""]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="scratch directory, outside output/")
    ap.add_argument("--cca-site", default=os.path.join(PROJECT_DIR, "..", "cca-site"))
    ap.add_argument("--baseline-ref", default="fbd5b02",
                    help="commit whose standings rows, since deleted, are also compared")
    args = ap.parse_args(argv)
    out = os.path.abspath(args.out)
    if os.path.commonpath([out, os.path.abspath(OUTPUT_DIR)]) == os.path.abspath(OUTPUT_DIR):
        ap.error("--out must be outside output/")
    content = os.path.join(args.cca_site, "content")

    events = read_events(content)
    folders = [Folder(slug, names + (legacy_standings_name(slug),)) for slug, names in events.items()]
    years = spelling_years(OUTPUT_DIR)
    spellings = folder_spellings(folders, years, canonicalize_family)
    report = build_rows(read_editions(content), folders, spellings, years)

    os.makedirs(out, exist_ok=True)
    write_standings(os.path.join(out, STANDINGS_CSV), report.rows)

    committed = _committed_rows()
    keys = {(r["tournament_name"], r["year"]) for r in committed}
    deleted = [r for r in _committed_rows(args.baseline_ref)
               if (r["tournament_name"], r["year"]) not in keys]
    lines = (_summary_lines(report)
             + render_final_counts(*against_final_counts(report.rows, final_counts(OUTPUT_DIR)))
             + render("Against the committed rows", compare(committed, report.rows))
             + render(f"Against rows in {args.baseline_ref} since deleted", compare(deleted, report.rows)))
    with open(os.path.join(out, "agreement.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    print(f"{len(report.rows)} rows and agreement.md written to {out}")


if __name__ == "__main__":
    main()
