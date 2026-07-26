"""Refresh tournament_summary.final_count against the live daily_scrape peak.

This is the export-free subset of 01_data_prep.py's reconciliation. 01_data_prep
rebuilds the whole summary from ~/Downloads/all_registrations.csv and can only run
when that manual export is present; this module instead loads the *existing*
tournament_summary.csv and bumps each event's final_count to max(snapshot, scrape
peak), using daily_scrape.csv alone.

Why it exists: without it, whenever the CCA export is missing (every CI run — the
export lives only on the operator's machine) completed events keep their stale
early-registration final_count. The moment such an event's end_date passes,
04e_performance_data.py's assert_truth_label_freshness guard aborts the pipeline
because the live scrape recorded far more entries than the frozen truth label
(June 2026: Hartford 63 vs 206, Cleveland 49 vs 174). Running this in the
missing-export branch keeps existing events' truth labels fresh; only the set of
*new* tournaments stays frozen until the next export.

The final_count rule here is identical to 01_data_prep.py lines 215-218 so the two
paths can never disagree on the value the guard checks. It deliberately does NOT
touch last_reg or extend daily_counts — that rebase needs the per-registration
rows from the export and stays in 01_data_prep.
"""

import os
import re

import pandas as pd

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def reconcile_final_counts(output_dir=OUTPUT_DIR, verbose=True):
    """Bump tournament_summary.final_count to the daily_scrape peak where higher,
    and append roster-pending skeletons for scraped events missing from summary.

    Returns the number of tournaments changed (final_count raised OR newly
    appended). No-ops (and returns 0) if either input CSV is missing, so it is
    safe to call blindly.
    """
    summary_path = os.path.join(output_dir, "tournament_summary.csv")
    scrape_path = os.path.join(output_dir, "daily_scrape.csv")
    if not os.path.exists(summary_path):
        if verbose:
            print(f"  Reconcile skipped — {summary_path} not found.")
        return 0
    if not os.path.exists(scrape_path):
        if verbose:
            print(f"  Reconcile skipped — {scrape_path} not found.")
        return 0

    summary = pd.read_csv(summary_path)
    scrape = pd.read_csv(scrape_path)

    # Peak entry_count per tournament_name (gross, includes withdrawn — matches
    # the row-count semantics of all_registrations.csv / final_count).
    scrape_peak = (scrape.groupby("tournament_name")["entry_count"]
                         .max()
                         .reset_index()
                         .rename(columns={"entry_count": "scrape_peak"}))
    summary = summary.merge(scrape_peak, on="tournament_name", how="left")

    pre_count = summary["final_count"].copy()
    summary["final_count"] = summary[["final_count", "scrape_peak"]].max(axis=1)
    summary["final_count"] = summary["final_count"].astype(int)
    bumped = summary[summary["final_count"] > pre_count].copy()
    summary = summary.drop(columns=["scrape_peak"])

    # H2: append roster-pending skeletons for scraped tournaments with no summary
    # row yet. Without this, a 2026 event whose registration opened after the last
    # all_registrations.csv export is invisible to the whole pipeline — 04e never
    # grades it and the freshness guard has no row to check — until the operator
    # runs a manual export. The skeleton carries has_timestamps=False, so every
    # 04c/04e training and grading filter (all of which require has_timestamps)
    # excludes it automatically; only a real export supplies the per-registration
    # timestamps needed to model or grade it. final_count is the gross scrape peak.
    known_names = set(summary["tournament_name"])
    tid_max = summary["tid"].max()
    next_tid = (int(tid_max) + 1) if len(summary) and pd.notna(tid_max) else 1
    new_rows = []
    for _, r in scrape_peak.iterrows():
        name = r["tournament_name"]
        peak = int(r["scrape_peak"])
        if name in known_names or peak <= 0:
            continue
        # Derive year + family from the "YYYY " prefix the scraper writes.
        m = re.match(r"^(\d{4})\s+(.*)$", str(name))
        if not m:
            continue
        new_rows.append({
            "tid": next_tid, "tournament_name": name, "family": m.group(2),
            "tournament_year": int(m.group(1)), "final_count": peak,
            "has_timestamps": False, "ts_count": 0, "first_reg": pd.NA,
            "last_reg": pd.NA, "is_covid": False, "is_online": False,
            "snapshot_last_reg": pd.NA, "early_bird_spike": False,
            "spike_day": pd.NA, "spike_magnitude": pd.NA, "roster_pending": True,
        })
        next_tid += 1

    if new_rows:
        if "roster_pending" not in summary.columns:
            summary["roster_pending"] = False
        new_df = pd.DataFrame(new_rows)
        if summary.empty:
            summary = new_df
        else:
            # pandas deprecates concat when a frame carries empty/all-NA
            # columns, and the pd.NA skeleton fields above are all-NA by
            # construction. Drop them and let the column union restore them
            # with summary's dtypes.
            summary = pd.concat([summary, new_df.dropna(axis=1, how="all")],
                                ignore_index=True)

    if verbose:
        if len(bumped) > 0:
            bumped["delta"] = bumped["final_count"] - pre_count[bumped.index]
            print(f"  Reconciled final_count for {len(bumped)} tournament(s):")
            for _, r in bumped.sort_values("delta", ascending=False).iterrows():
                print(f"    {r['tournament_name']:<55} "
                      f"snapshot={pre_count[r.name]:>5} → scrape={r['final_count']:>5} "
                      f"(+{int(r['delta'])})")
        else:
            print("  No final_count reconciliation needed.")
        if new_rows:
            print(f"  Added {len(new_rows)} roster-pending tournament(s) not yet in summary:")
            for nr in new_rows:
                print(f"    {nr['tournament_name']:<55} scrape_peak={nr['final_count']:>5} "
                      f"(has_timestamps=False)")

    if len(bumped) > 0 or new_rows:
        summary.to_csv(summary_path, index=False)
    return len(bumped) + len(new_rows)


if __name__ == "__main__":
    n = reconcile_final_counts()
    print(f"Done — {n} tournament(s) reconciled.")
