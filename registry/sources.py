"""Which files the registry resolves, and how each one names an edition."""
from registry.exemptions import (fee_exemption, historical_exemption, ledger_exemption,
                                 scrape_exemption, summary_exemption)
from registry.keys import (fee_edition_key, flyer_code, historical_edition_key,
                           scrape_edition_key, standings_edition_key, summary_edition_key)
from registry.resolve import Source
from shared.editions import split_edition_name
from tournament_aliases import canonicalize_family

SUMMARY = "tournament_summary.csv"
METADATA = "tournament_metadata.csv"


def _fee_year_note(row, edition):
    if row["year"] != edition[1]:
        return f"year column {row['year']} disagrees with the URL's {edition[1]}"
    return None


def _name_year_note(row, edition):
    named = split_edition_name(row["tournament_name"])[1]
    if named is not None and named != edition[1]:
        return f"{row['tournament_name']!r} is filed under {edition[1]}, the year of its start_date"
    return None

SOURCES = (
    Source(SUMMARY,
           edition_of=lambda r: summary_edition_key(r["family"], r["tournament_year"]),
           label=lambda r: str(r["tid"]),
           exemption_of=summary_exemption, column="tids"),
    Source(METADATA,
           edition_of=lambda r: summary_edition_key(r["family"], r["year"]),
           label=lambda r: r["family"], column="metadata_names"),
    Source("daily_scrape.csv",
           edition_of=lambda r: scrape_edition_key(r["tournament_name"]),
           label=lambda r: r["tournament_name"], exemption_of=scrape_exemption,
           unique=False, column="scrape_names"),
    Source("tournament_fees.csv",
           edition_of=lambda r: fee_edition_key(r["url"]),
           label=lambda r: r["url"],
           exemption_of=lambda r: fee_exemption(flyer_code(r["url"])),
           warning_of=_fee_year_note, column="fee_urls"),
    Source("historical_standings.csv",
           edition_of=lambda r: standings_edition_key(r["tournament_name"], r["year"]),
           label=lambda r: r["tournament_name"], column="standings_names"),
    # Lists every CCA event, including one-offs (ICC online, monthly
    # actions) that belong to no family the model tracks.
    Source("historical_tournaments.csv",
           edition_of=lambda r: historical_edition_key(r["tournament_name"], r["year"]),
           label=lambda r: r["tournament_name"],
           exemption_of=historical_exemption, warning_of=_name_year_note,
           unknown_family_rule="outside the tracked families", column="historical_names"),
    Source("walk_in_multipliers.csv",
           edition_of=lambda r: summary_edition_key(r["family"], r["year"]),
           label=lambda r: r["family"]),
    Source("forecast_ledger.csv",
           edition_of=lambda r: summary_edition_key(r["family"], r["year"]),
           label=lambda r: r["family"], exemption_of=ledger_exemption, unique=False),
    Source("forecast_ledger_backfill.csv",
           edition_of=lambda r: summary_edition_key(r["family"], r["year"]),
           label=lambda r: r["family"], exemption_of=ledger_exemption, unique=False),
)


def families(frames):
    """Every tracked family: the canonical families of the summary and the
    metadata, leaving out the exempt summary rows (legacy names such as "42nd
    annual Continental Open"). The metadata gains a row for each newly scraped edition, so a
    new CCA event is a family from its first night."""
    summary = [r["family"] for r in frames[SUMMARY].to_dict("records") if not summary_exemption(r)]
    names = summary + list(frames[METADATA]["family"])
    return {canonicalize_family(n) for n in names if isinstance(n, str)}
