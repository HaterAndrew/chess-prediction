"""Cross-engine thresholds that were duplicated per module.

A fold is only comparable across the two grading engines (04e main model,
window_grading second engine) and the data-health scanner when they agree on
these values — the duplicates had already been annotated with keep-in-sync
comments, which is the tell that they belong in one place.
"""

# Minimum final_count for a tournament to enter grading corpora.
MIN_FINAL_COUNT = 50

# A historical daily curve whose scrape peak covers less than this fraction
# of final_count is treated as frozen/partial (04e fold gate). data_health
# deliberately keeps its OWN 0.60 literal (PERF_FROZEN_CURVE_RATIO): the
# scanner is a watchdog on 04e and must keep reporting if the two drift.
FROZEN_CURVE_MIN_RATIO = 0.60
