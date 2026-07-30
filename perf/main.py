"""04e orchestrator: prepare folds, run year folds, build the report."""
from perf.folds import prepare_folds, run_year_folds
from perf.report import build_report


def main():
    summary, daily, meta, enrichment_lookup, completed_2026_tids = prepare_folds()
    year_results, all_tournament_results = run_year_folds(
        summary, daily, meta, enrichment_lookup, completed_2026_tids)
    build_report(summary, year_results, all_tournament_results)


if __name__ == "__main__":
    main()
