"""The corpus 04e grades from, and the evaluation frame the window grade scores on.

The leave-one-out fold and the outcome-selected tiers that admitted 2026 events
are gone: every graded forecast now comes from the walk-forward
(perf.walkforward), which chooses events by their dates alone.
"""
from corpus import load_corpus
from shared.paths import OUTPUT_DIR
from shared.season import eval_years
from shared.side_events import SIDE_EVENT_PATTERN
from tournament_aliases import is_wo_excluded

from perf.evaluation import assert_truth_label_freshness
from perf.wf_events import WO_PERF_EXTRA

# The seasons the window grade scores. Derived from the season so the list
# keeps growing instead of stopping at a literal final year.
EVAL_YEARS = eval_years(first=2022)


def evaluation_summary(summary):
    """The summary without quick-chess side events and World Open sub-events.

    Side events follow a different registration regime (shared.side_events).
    World Open sub-events inherit the combined World Open's history, ten times
    their size (tournament_aliases.is_wo_excluded, the same rule as 04d).
    """
    side = summary['family'].str.contains(SIDE_EVENT_PATTERN, case=False, na=False, regex=True)
    if side.any():
        names = summary.loc[side, 'family'].unique()
        print(f"  Excluding {len(names)} blitz/rapid families: {', '.join(names)}")
    wo = summary['family'].map(lambda f: is_wo_excluded(f) or f in WO_PERF_EXTRA).astype(bool)
    if (wo & ~side).any():
        print(f"  Excluding {summary.loc[wo & ~side, 'family'].nunique()} "
              f"World Open sub-events from perf eval")
    return summary[~side & ~wo].copy()


def prepare_folds():
    """The corpus, after the truth-label check, and its evaluation summary."""
    corpus = load_corpus(OUTPUT_DIR)
    assert_truth_label_freshness(corpus.summary)
    return corpus, evaluation_summary(corpus.summary)
