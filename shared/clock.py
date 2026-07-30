"""One place to read "today".

Three functions because the three frozen-at-import TODAY types across the
pipeline are load-bearing (04c compares datetimes, 04d/04e compare pandas
Timestamps, scrape_entries writes ISO strings). Consumers keep their
`TODAY = clock.today_X()` at module top — freeze-at-import semantics are
deliberately unchanged by the decomposition; this only gives tests a single
seam to patch and stops new variants from appearing.
"""

from datetime import date, datetime

import pandas as pd


def today_dt() -> datetime:
    return datetime.now()


def today_ts() -> pd.Timestamp:
    return pd.Timestamp.now().normalize()


def today_date() -> date:
    return date.today()


def today_iso() -> str:
    return date.today().isoformat()
