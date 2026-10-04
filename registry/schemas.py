"""Column contracts for the files the registry reads (pandera).

Key columns only: their presence, dtype, nullability and range. Other
columns are free to change without touching this file (strict=False).
"""
import pandera.pandas as pa

DATE = pa.Check.str_matches(r"^\d{4}-\d{2}-\d{2}$")
YEAR = pa.Check.in_range(1970, 2100)
COUNT = pa.Check.ge(0)


def _schema(columns):
    return pa.DataFrameSchema(columns, strict=False, coerce=False)


SCHEMAS = {
    "tournament_summary.csv": _schema({
        "tid": pa.Column(int, unique=True),
        "family": pa.Column(str),
        # Null for the legacy and non-edition tids (registry.exemptions).
        "tournament_year": pa.Column(float, YEAR, nullable=True),
        "final_count": pa.Column(int, COUNT),
    }),
    "tournament_metadata.csv": _schema({
        "family": pa.Column(str),
        "year": pa.Column(int, YEAR),
        "start_date": pa.Column(str, DATE),
        "end_date": pa.Column(str, DATE),
    }),
    "daily_scrape.csv": _schema({
        "date": pa.Column(str, DATE),
        "tournament_name": pa.Column(str),
        "entry_count": pa.Column(int, COUNT),
        "url": pa.Column(str),
    }),
    "tournament_fees.csv": _schema({
        "tournament_name": pa.Column(str),
        "year": pa.Column(int, YEAR),
        "url": pa.Column(str, unique=True),
    }),
    "historical_standings.csv": _schema({
        "tournament_name": pa.Column(str),
        "year": pa.Column(int, YEAR),
        "total_players": pa.Column(int, COUNT),
    }),
    "historical_tournaments.csv": _schema({
        "tournament_name": pa.Column(str),
        "year": pa.Column(int, YEAR),
        "total_entries": pa.Column(int, COUNT),
    }),
    "walk_in_multipliers.csv": _schema({
        "family": pa.Column(str),
        "year": pa.Column(int, YEAR),
        "walk_in_ratio": pa.Column(float, pa.Check.gt(0)),
    }),
    "forecast_ledger.csv": _schema({
        "family": pa.Column(str),
        "year": pa.Column(int, YEAR),
    }),
    "forecast_ledger_backfill.csv": _schema({
        "family": pa.Column(str),
        "year": pa.Column(int, YEAR),
    }),
}


def schema_errors(file, frame, limit=5):
    """One line per failed check, at most `limit` failure cases each."""
    try:
        SCHEMAS[file].validate(frame, lazy=True)
    except pa.errors.SchemaErrors as e:
        cases = e.failure_cases
        lines = []
        for (column, check), group in cases.groupby(["column", "check"], dropna=False, sort=False):
            sample = ", ".join(str(v) for v in group["failure_case"].head(limit))
            lines.append(f"{file}: {column} fails {check} ({len(group)} row(s): {sample})")
        return lines
    return []
