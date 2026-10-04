"""How far rebuilt standings rows sit from rows already committed.

Rows pair on the registry's edition key, so "Bostonchess Congress" 2019
pairs with "Boston Chess Congress" 2019. For each pair the report gives the
old total, the old total without the side-event sections by name, and the
new total: the first gap is the count rule's whole effect, the second the
part re-listed sections and unique-player counting explain. "Not in
cca-site" names main sections the old row has and the rebuilt row lacks.

Rebuilt rows are also set against the summary's final pre-registration
count, which a main-sections count should sit near: walk-ins add players,
withdrawals remove a few.
"""
import json
import re
from dataclasses import dataclass, field

from registry.keys import standings_edition_key
from standings.count_rule import is_side_event_section

FINAL_COUNT_BAND = (0.8, 1.5)


@dataclass(frozen=True)
class Pair:
    key: tuple
    old_total: int
    old_main: object        # int, or None when the old sections do not parse
    new_total: int
    not_in_ccasite: tuple


@dataclass
class Agreement:
    pairs: list = field(default_factory=list)
    old_only: list = field(default_factory=list)    # keys with no rebuilt row


def _sections(row):
    try:
        return json.loads(row.get("sections") or "{}")
    except (TypeError, ValueError):
        return None


def _section_key(name):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\s*section\b", "", name.casefold()))


def _pair(key, old, new):
    old_sections = _sections(old)
    if old_sections is None:
        return Pair(key, int(old["total_players"]), None, int(new["total_players"]), ())
    main = {n: c for n, c in old_sections.items() if not is_side_event_section(n)}
    have = {_section_key(n) for n in _sections(new) or {}}
    lacking = tuple(n for n in main if _section_key(n) not in have)
    return Pair(key, int(old["total_players"]), sum(main.values()),
                int(new["total_players"]), lacking)


def compare(old_rows, new_rows):
    new = {standings_edition_key(r["tournament_name"], r["year"]): r for r in new_rows}
    out = Agreement()
    for row in old_rows:
        key = standings_edition_key(row["tournament_name"], int(row["year"]))
        if key in new:
            out.pairs.append(_pair(key, row, new[key]))
        else:
            out.old_only.append(key)
    out.pairs.sort(key=lambda p: (-abs(p.new_total - p.old_total), p.key))
    return out


def render(title, agreement):
    pairs = agreement.pairs
    equal = sum(1 for p in pairs if p.old_total == p.new_total)
    near = sum(1 for p in pairs if p.old_total and abs(p.new_total - p.old_total) <= 0.02 * p.old_total)
    lines = [f"## {title}", "",
             f"{len(pairs)} paired, {equal} equal, {near} within 2%, "
             f"{len(agreement.old_only)} with no rebuilt row.", ""]
    if agreement.old_only:
        lines += ["No rebuilt row: " + "; ".join(f"{f} {y}" for f, y in sorted(agreement.old_only)), ""]
    lines += ["| Edition | Old total | Old without side events | New total | New / old | Not in cca-site |",
              "|---|---:|---:|---:|---:|---|"]
    for p in pairs:
        ratio = f"{p.new_total / p.old_total:.2f}" if p.old_total else "-"
        old_main = "" if p.old_main is None else p.old_main
        lines.append(f"| {p.key[0]} {p.key[1]} | {p.old_total} | {old_main} | {p.new_total} "
                     f"| {ratio} | {', '.join(p.not_in_ccasite)} |")
    return lines + [""]


def against_final_counts(new_rows, finals):
    """(inside the band, [(key, final, new) outside it]) for rebuilt rows whose
    edition has a final count. finals: {edition key: final_count}."""
    low, high = FINAL_COUNT_BAND
    inside, outside = 0, []
    for row in new_rows:
        key = standings_edition_key(row["tournament_name"], row["year"])
        final = finals.get(key)
        if not final:
            continue
        if low <= row["total_players"] / final <= high:
            inside += 1
        else:
            outside.append((key, final, row["total_players"]))
    return inside, sorted(outside, key=lambda o: o[2] / o[1])


def render_final_counts(inside, outside):
    low, high = FINAL_COUNT_BAND
    lines = ["## Against the summary's final count", "",
             f"{inside} rebuilt rows within {low}-{high} times the final count, "
             f"{len(outside)} outside.", "",
             "| Edition | Final count | New total | New / final |", "|---|---:|---:|---:|"]
    lines += [f"| {f} {y} | {final} | {new} | {new / final:.2f} |" for (f, y), final, new in outside]
    return lines + [""]
