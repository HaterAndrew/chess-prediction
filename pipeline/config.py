"""Pipeline-wide paths and run constants (auto_update head, verbatim
derivations). Moved functions read these as config.X attributes at call
time, so a test that monkeypatches pipeline.config.SITE_DIR redirects
every derived write in the same run.
"""
import os
from datetime import datetime

# The repo root -- auto_update.py used dirname(__file__); this module
# lives one level down, so take the shared constant instead.
from shared.paths import PROJECT_DIR  # noqa: F401

OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
SITE_DIR = os.path.join(PROJECT_DIR, "docs")
SCRAPE_CSV = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
WEBSITE_JSON = os.path.join(OUTPUT_DIR, "website_data.json")
# Kept for callers that want the default location; the stampers derive their
# own targets from SITE_DIR at write time (see _stamp_targets) so redirecting
# SITE_DIR redirects the write too.
INDEX_HTML = os.path.join(SITE_DIR, "index.html")
# The large data consts were externalized out of index.html (L15); the daily
# build now splices them into this file, so index.html itself stays static.
SITE_DATA_JS = os.path.join(SITE_DIR, "data", "site_data.js")
# Raw JSON served by Pages for the Ask Worker (v3 S1). Kept for callers that
# want the default location; step_update_html derives its own from SITE_DIR at
# write time so redirecting SITE_DIR redirects the write too. A module constant
# frozen at import cannot be redirected, and that is how a test ended up
# overwriting the published endpoint.
SITE_DATA_JSON = os.path.join(SITE_DIR, "data", "website_data.json")
UPDATE_LOG = os.path.join(OUTPUT_DIR, "update_log.csv")

RUN_TS = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
