"""Freshness check on output/tournament_metadata.csv (AUDIT.md A3)."""
import logging
import os

import pandas as pd

from fees.codes import flyer_code_for
from shared.paths import METADATA_CSV
from validation.report import ValidationReport

logger = logging.getLogger(__name__)


def _scraped_flyer_urls(meta_path, report):
    """Every scraped flyer URL. A missing fees file or url column is reported:
    without it every event would read as "no flyer scraped yet"."""
    fees_path = os.path.join(os.path.dirname(meta_path), "tournament_fees.csv")
    if not os.path.exists(fees_path):
        report.add_warning(f"{fees_path} not found; flyer coverage cannot be checked")
        return []
    fees = pd.read_csv(fees_path)
    if "url" not in fees.columns:
        report.add_warning(f"{fees_path} has no url column; flyer coverage cannot be checked")
        return []
    return fees["url"].dropna().astype(str).tolist()


def _has_flyer(family, yy, urls):
    """A flyer is scraped when a fee row's URL is the family's <code><yy>
    page. merge_fees matches on the URL too: tournament_name holds the page
    title when the parser found one ("Midwest Class"), so it cannot carry
    the code."""
    code = flyer_code_for(family)
    if not code:
        return False
    needle = f"/{code}{yy}."
    return any(needle in u for u in urls)


def _classify(families, yy, urls):
    """Split families into (flyer scraped, no flyer code, no flyer yet)."""
    scraped, no_code, unknown = [], [], []
    for fam in families:
        if not flyer_code_for(fam):
            no_code.append(fam)
        elif _has_flyer(fam, yy, urls):
            scraped.append(fam)
        else:
            unknown.append(fam)
    return scraped, no_code, unknown


def validate_metadata_freshness(csv_path=None, year=None):
    """Surface upcoming events with degraded model features (missing early-bird
    deadline). The deadline drives days_to_early_bird in feature_engineering;
    when missing, the model uses neutral values — silent degradation.
    AUDIT.md A3.
    """
    report = ValidationReport()
    if csv_path is None:
        csv_path = METADATA_CSV
    if not os.path.exists(csv_path):
        report.add_warning(f"{csv_path} not found")
        return report
    m = pd.read_csv(csv_path)
    m['start_date'] = pd.to_datetime(m['start_date'], errors='coerce')
    m['early_bird_deadline'] = pd.to_datetime(m['early_bird_deadline'], errors='coerce')
    today = pd.Timestamp.now().normalize()
    if year is None:
        year = today.year
    this_year = m[m['year'] == year]
    undated = this_year[this_year['start_date'].isna()]
    if len(undated):
        report.add_warning(
            f"{len(undated)} {year} event(s) have no parseable start_date and were "
            f"not checked: {', '.join(sorted(undated['family'].astype(str)))}"
        )
    upcoming = this_year[this_year['start_date'] > today]
    no_eb = upcoming[upcoming['early_bird_deadline'].isna()]
    if len(no_eb) == 0:
        return report

    # v5 follow-up: "missing" hid two different truths. If the year's flyer IS
    # scraped and carries no early-bird tier (chesstour's modern advance/onsite
    # step gets demoted by scrape_fees' T-window rule), the absence is verified
    # source truth — merge_fees would have filled it otherwise — and warning
    # about it nightly is noise. Only events with NO flyer scraped yet are
    # actionably unknown.
    urls = _scraped_flyer_urls(csv_path, report)
    verified_absent, no_code, unknown = _classify(no_eb['family'].astype(str), str(year)[2:], urls)

    if verified_absent:
        logger.info(
            f"{len(verified_absent)} upcoming {year} event(s) verified no early-bird "
            f"tier on the scraped flyer (neutral EB features are correct): "
            f"{', '.join(sorted(verified_absent))}"
        )
    if no_code:
        report.add_warning(
            f"{len(no_code)} upcoming {year} event(s) have no flyer code in "
            f"fees/codes.py, so their fees and early-bird deadline cannot fill "
            f"from a flyer: {', '.join(sorted(no_code))}"
        )
    if unknown:
        report.add_warning(
            f"{len(unknown)} upcoming {year} event(s) have no flyer scraped yet — "
            f"early_bird_deadline unknown, model uses neutral feature values "
            f"(fees + EB fill automatically once chesstour publishes the flyer): "
            f"{', '.join(sorted(unknown))}"
        )
    return report
