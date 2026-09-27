"""Read the corpus once, for the site builder and the backtest alike."""
import os

import pandas as pd

from model.data_io import reanchor_daily_to_event_start
from shared.paths import OUTPUT_DIR

from corpus.view import Corpus


def read_written(output_dir=OUTPUT_DIR):
    """Summary, daily curves and metadata as written; curves anchored at last_reg."""
    summary = pd.read_csv(os.path.join(output_dir, "tournament_summary.csv"))
    daily = pd.read_csv(os.path.join(output_dir, "daily_registration_counts.csv"))
    meta = pd.read_csv(os.path.join(output_dir, "tournament_metadata.csv"))
    return summary, daily, meta


def _optional(output_dir, name):
    path = os.path.join(output_dir, name)
    return pd.read_csv(path) if os.path.exists(path) else None


def load_corpus(output_dir=OUTPUT_DIR):
    """Every source the models read, curves anchored at event start.

    Missing optional files: no standings or scrape (None), an empty
    enrichment frame.
    """
    summary, daily, meta = read_written(output_dir)
    # T=0 at event start, during-event rows dropped: the model trains and
    # predicts on pre-start registrations only.
    daily = reanchor_daily_to_event_start(summary, daily, meta)
    meta['start_date'] = pd.to_datetime(meta['start_date'])
    enrichment = _optional(output_dir, "historical_tournaments.csv")
    return Corpus(summary=summary, daily=daily, meta=meta,
                  standings=_optional(output_dir, "historical_standings.csv"),
                  enrichment=enrichment if enrichment is not None else pd.DataFrame(),
                  scrape=_optional(output_dir, "daily_scrape.csv"))
