"""Phase-1 orchestrator: load, families, summary, reconcile, curves,
spikes, save, report -- same order as the original imperative script.
"""
import os

from shared.paths import OUTPUT_DIR

from dataprep.curves import build_daily_counts, extend_with_scrape
from dataprep.families import annotate_families
from dataprep.loading import load_registrations
from dataprep.reporting import (dq_check, eda_chicago, eda_family_stats,
                                eda_yearly, final_stats, save_outputs)
from dataprep.spikes import annotate_spikes
from dataprep.summary import build_summary, reconcile_with_scrape


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = load_registrations()
    df = annotate_families(df)
    summary, tid_merge_map = build_summary(df)
    summary, rebased_tids, scrape_for_extension = reconcile_with_scrape(summary)
    daily_counts = build_daily_counts(df, summary, tid_merge_map)
    daily_counts = extend_with_scrape(daily_counts, summary, rebased_tids,
                                      scrape_for_extension)
    summary, n_spikes = annotate_spikes(summary, daily_counts)
    save_outputs(summary, daily_counts)
    dq_check(summary, daily_counts)
    eda_chicago(summary, daily_counts)
    family_counts = eda_family_stats(summary)
    eda_yearly(summary)
    final_stats(summary, family_counts, n_spikes)


if __name__ == "__main__":
    main()
