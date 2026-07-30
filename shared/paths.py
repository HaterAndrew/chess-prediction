"""Single home for repo paths and named data artifacts.

Replaces the per-module PROJECT_DIR/OUTPUT_DIR recomputation (25 modules) and
the tournament_summary.csv path literal (13 modules). Modules adopt these as
they are touched by the decomposition — a big-bang replace would churn every
file for no behavior gain.

Artifact FILENAMES are load-bearing: daily_update.yml's git-add list, the
degraded-banner heredoc, and the CI step summary all key on them. Renaming
any constant's value requires updating the workflow in the same commit.
"""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
DOCS_DIR = os.path.join(PROJECT_DIR, "docs")

SUMMARY_CSV = os.path.join(OUTPUT_DIR, "tournament_summary.csv")
DAILY_COUNTS_CSV = os.path.join(OUTPUT_DIR, "daily_registration_counts.csv")
METADATA_CSV = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
SCRAPE_CSV = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
FEES_CSV = os.path.join(OUTPUT_DIR, "tournament_fees.csv")
WEBSITE_JSON = os.path.join(OUTPUT_DIR, "website_data.json")
PERFORMANCE_JSON = os.path.join(OUTPUT_DIR, "performance_data.json")
UPDATE_LOG_CSV = os.path.join(OUTPUT_DIR, "update_log.csv")
