"""The integrity check and the registry table, from loaded frames. Pure."""
import pandas as pd

from registry.resolve import resolve_source
from registry.schemas import schema_errors
from registry.sources import METADATA, SOURCES, SUMMARY, families
from validation.report import ValidationReport

REGISTRY_COLUMNS = ["family", "year"] + [s.column for s in SOURCES if s.column]


def _contract_errors(frames):
    """{file: [errors]} for files that are missing, empty, or fail their
    column contract."""
    failed = {}
    for source in SOURCES:
        frame = frames.get(source.file)
        if frame is None:
            failed[source.file] = [f"{source.file} not found"]
        elif frame.empty:
            failed[source.file] = [f"{source.file} has no rows"]
        else:
            errors = schema_errors(source.file, frame)
            if errors:
                failed[source.file] = errors + [
                    f"{source.file}: rows not resolved until its columns pass"]
    return failed


def check_integrity(frames):
    """(report, resolutions). Errors: a missing or empty file, a failed
    column contract, a row that resolves to no edition, two rows for one
    edition. Warnings: a resolved row whose own year columns disagree.
    Exemptions are counted per rule in each resolution."""
    report = ValidationReport()
    failed = _contract_errors(frames)
    for errors in failed.values():
        for line in errors:
            report.add_error(line)
    if SUMMARY in failed or METADATA in failed:
        report.add_error("no file resolved: the family universe comes from the summary and metadata")
        return report, []

    universe = families(frames)
    resolutions = []
    for source in SOURCES:
        if source.file in failed:
            continue
        resolution = resolve_source(source, frames[source.file], universe)
        for line in resolution.unresolved + resolution.duplicates:
            report.add_error(line)
        for line in resolution.warnings:
            report.add_warning(line)
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
