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

from tournament_aliases import canonicalize_family

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# The scraper writes names like "2026 World Open, top 6 sections".
_YEAR_PREFIX_RE = re.compile(r"^(\d{4})\s+(.*)$")


def _scrape_key(name):
    """(canonical family, year) for a scraped tournament_name, or None.

    The export and the scraper spell the same event differently ("World Open
    top 6 sections" with a double space vs "World Open, top 6 sections" with a
    comma), so identity checks against summary rows must go through
    canonicalize_family — exact tournament_name matching created duplicate
    rows (audit v5 Cat R).
    """
    m = _YEAR_PREFIX_RE.match(str(name))
    if not m:
        return None
    return canonicalize_family(m.group(2)), int(m.group(1))


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
    summary = summary.drop(columns=["scrape_peak"])

    # Canonical-family fallback for scrape names with no exact summary row:
    # the exact-name merge above misses rows whose export spelling differs
    # from the scraper's (comma/whitespace variants). Without this pass those
    # real rows keep a stale final_count and 04e's freshness guard goes blind
    # to them once the skeleton duplicates are healed below.
    summary_keys = [
        (canonicalize_family(str(f)), int(y)) if pd.notna(y) else None
        for f, y in zip(summary["family"], summary["tournament_year"])
    ]
    for _, r in scrape_peak.iterrows():
        name = r["tournament_name"]
        if name in set(summary["tournament_name"]):
            continue  # exact merge already handled it
        key = _scrape_key(name)
        if key is None:
            continue
        peak = int(r["scrape_peak"])
        for idx, skey in zip(summary.index, summary_keys):
            if skey == key and peak > summary.at[idx, "final_count"]:
                summary.at[idx, "final_count"] = peak

    bumped = summary[summary["final_count"] > pre_count].copy()

    # Self-heal duplicate rows: a roster-pending skeleton whose canonical
    # (family, year) collides with a real export-derived row is the artifact
    # of the old exact-name join. Keep the real row (it carries timestamps),
    # give it the group's max final_count, drop the skeleton(s). Idempotent —
    # safe to run nightly. Never drops a real row.
    healed = []
    if "roster_pending" in summary.columns:
        pend = summary["roster_pending"].map(
            lambda v: bool(v) if pd.notna(v) else False)
        groups = {}
        for idx, skey in zip(summary.index, summary_keys):
            if skey is not None:
                groups.setdefault(skey, []).append(idx)
        drop_idx = []
        for key, idxs in groups.items():
            if len(idxs) < 2:
                continue
            skel = [i for i in idxs if pend.loc[i]]
            real = [i for i in idxs if not pend.loc[i]]
            if not skel or not real:
                continue
            group_max = int(summary.loc[idxs, "final_count"].max())
            # Keeper: prefer the real row whose family string IS the canonical
            # form (the post-split series row), not one merely folded onto it
            # by an alias (e.g. pre-split "World Open" canonicalizes onto
            # "World Open top 6 sections" for history comparison but is a
            # different row). Deterministic tie-break by position.
            real.sort(key=lambda i: (summary.at[i, "family"] != key[0], i))
            keeper = real[0]
            if group_max > summary.at[keeper, "final_count"]:
                summary.at[keeper, "final_count"] = group_max
            drop_idx.extend(skel)
            healed.append((key, summary.at[keeper, "tournament_name"],
                           [summary.at[i, "tournament_name"] for i in skel],
                           group_max))
        if drop_idx:
            summary = summary.drop(index=drop_idx).reset_index(drop=True)

    # H2: append roster-pending skeletons for scraped tournaments with no summary
    # row yet. Without this, a 2026 event whose registration opened after the last
    # all_registrations.csv export is invisible to the whole pipeline — 04e never
    # grades it and the freshness guard has no row to check — until the operator
    # runs a manual export. The skeleton carries has_timestamps=False, so every
    # 04c/04e training and grading filter (all of which require has_timestamps)
    # excludes it automatically; only a real export supplies the per-registration
    # timestamps needed to model or grade it. final_count is the gross scrape peak.
    known_names = set(summary["tournament_name"])
    # Canonical identity too: a scrape name that spells an existing event
    # differently (comma variant) must not spawn a duplicate skeleton.
    known_keys = {
        (canonicalize_family(str(f)), int(y))
        for f, y in zip(summary["family"], summary["tournament_year"])
        if pd.notna(y)
    }
    tid_max = summary["tid"].max()
    next_tid = (int(tid_max) + 1) if len(summary) and pd.notna(tid_max) else 1
    new_rows = []
    for _, r in scrape_peak.iterrows():
        name = r["tournament_name"]
        peak = int(r["scrape_peak"])
        if name in known_names or peak <= 0:
            continue
        # Derive year + family from the "YYYY " prefix the scraper writes.
        m = _YEAR_PREFIX_RE.match(str(name))
        if not m:
            continue
        if (canonicalize_family(m.group(2)), int(m.group(1))) in known_keys:
            continue
        new_rows.append({
            # family is stored canonical so 04d's family joins, history lookups
            # and n_editions counts resolve; tournament_name stays scraper-exact
            # (04e's scrape joins depend on it).
            "tid": next_tid, "tournament_name": name,
            "family": canonicalize_family(m.group(2)),
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
        for key, kept, dropped, group_max in healed:
            print(f"  HEALED duplicate {key[1]} '{key[0]}': kept real row "
                  f"'{kept}' (final_count={group_max}), dropped skeleton(s) "
                  f"{dropped}")
        if new_rows:
            print(f"  Added {len(new_rows)} roster-pending tournament(s) not yet in summary:")
            for nr in new_rows:
                print(f"    {nr['tournament_name']:<55} scrape_peak={nr['final_count']:>5} "
                      f"(has_timestamps=False)")

    if len(bumped) > 0 or new_rows or healed:
        summary.to_csv(summary_path, index=False)
    return len(bumped) + len(new_rows) + len(healed)


if __name__ == "__main__":
    n = reconcile_final_counts()
    print(f"Done — {n} tournament(s) reconciled.")
