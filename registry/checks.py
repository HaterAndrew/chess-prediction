"""The integrity check and the registry table, from loaded frames. Pure."""
import pandas as pd

from registry.resolve import resolve_source
from registry.schemas import schema_errors
from registry.sources import SOURCES, families
from validation.report import ValidationReport

REGISTRY_COLUMNS = ["family", "year"] + [s.column for s in SOURCES if s.column]


def check_integrity(frames):
    """(report, resolutions). Errors: a missing file, a failed column
    contract, a row that resolves to no edition, two rows for one edition.
    Exemptions are counted per rule in each resolution."""
    report = ValidationReport()
    missing = [s.file for s in SOURCES if s.file not in frames]
    for file in missing:
        report.add_error(f"{file} not found")
    if missing:
        return report, []

    universe = families(frames)
    resolutions = []
    for source in SOURCES:
        errors = schema_errors(source.file, frames[source.file])
        for line in errors:
            report.add_error(line)
        if errors:
            continue  # rows cannot be keyed reliably until the contract holds
        resolution = resolve_source(source, frames[source.file], universe)
        for line in resolution.unresolved + resolution.duplicates:
            report.add_error(line)
        resolutions.append(resolution)
    return report, resolutions


def build_registry(resolutions):
    """One row per edition: its family and year, and each file's own keys for
    it, ';'-joined. Editions come from every listed file."""
    columns = {r.file: s.column for s in SOURCES for r in resolutions if r.file == s.file}
    table = {}
    for resolution in resolutions:
        column = columns.get(resolution.file)
        if not column:
            continue
        for edition, label in resolution.rows:
            table.setdefault(edition, {}).setdefault(column, set()).add(str(label))
    rows = [{"family": family, "year": year,
             **{col: ";".join(sorted(labels)) for col, labels in keys.items()}}
            for (family, year), keys in table.items()]
    frame = pd.DataFrame(rows, columns=REGISTRY_COLUMNS)
    return frame.sort_values(["family", "year"], ignore_index=True)


def exemption_lines(resolutions):
    """'file: n row(s) exempt as <rule>' for every exemption that applied."""
    return [f"{r.file}: {n} row(s) exempt as {rule}"
            for r in resolutions for rule, n in sorted(r.exempt.items())]
