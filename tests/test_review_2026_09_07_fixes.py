"""Regressions for the P1 correctness fixes from the 2026-09-07 review.

Each test fails against the code as it stood before the fix:

P1-2  fit() filtered standings by exclude_family_years using the RAW spelling,
      then renamed. 56 of the mapped names differ, so the 2026 leave-one-out
      fold kept the target's own standings row and leaked its size anchor.
P1-3  recalibrate() blanked _recal_bias/_recal_ci around predict_nowcast with
      no finally, so one raising tournament switched recalibration off for the
      rest of the model's life, silently.
P1-5  the Compare tab read t.event_date; the payload field is event_start, so
      every Event Date cell rendered the placeholder.
P1-6  BLITZ_FAMILIES was a class attribute that fit() mutated, so side-event
      classification leaked between model instances sharing an interpreter.
"""
import json
import os
import re
import sys

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from model.core import N5v4_Final  # noqa: E402
from tournament_aliases import STANDINGS_NAME_MAP  # noqa: E402


# ── P1-2: standings canonicalization must precede name-keyed filtering ──────

def _summary(rows):
    return pd.DataFrame(rows)


def _minimal_corpus():
    """One family with enough curve to produce ratios, and nothing else.

    'Kings Island Open' is deliberately absent so the standings supplement is
    the only thing that could introduce it into family_mean_final.
    """
    summary = _summary([
        {"tid": f"t{y}", "family": "Anchor Open", "final_count": 200,
         "tournament_year": y, "has_timestamps": True,
         "is_online": False, "is_covid": False, "last_reg": f"{y}-06-01"}
        for y in (2022, 2023, 2024)
    ])
    daily = pd.DataFrame([
        {"tid": f"t{y}", "T": T, "cum_regs": 100 + T}
        for y in (2022, 2023, 2024)
        for T in (90, 60, 42, 28, 14, 7, 3, 1)
    ])
    return summary, daily


@pytest.fixture
def standings_dir(tmp_path, monkeypatch):
    """Point fit()'s standings read at a synthetic file.

    Patches the module that DEFINES the name fit() reads (model.fitting pulled
    OUTPUT_DIR into its own namespace at import), per the repo's patching rule.
    """
    monkeypatch.setattr("model.fitting.OUTPUT_DIR", str(tmp_path))
    return tmp_path


def _write_standings(path, rows):
    pd.DataFrame(rows).to_csv(os.path.join(path, "historical_standings.csv"),
                              index=False)


def test_exclusion_matches_a_family_whose_standings_name_is_mapped(standings_dir):
    """The leak: raw 'Kingsisland Open' never matched canonical exclusion."""
    summary, daily = _minimal_corpus()
    _write_standings(standings_dir, [
        {"tournament_name": "Kingsisland Open", "year": 2026, "total_players": 500},
    ])

    m = N5v4_Final()
    m.fit(summary, daily, verbose_standings_join=False,
          exclude_family_years={("Kings Island Open", 2026)})

    assert "Kings Island Open" not in m.family_mean_final, (
        "the target's own 2026 standings row survived exclusion — size-anchor leak")


def test_exclusion_still_admits_a_year_it_does_not_name(standings_dir):
    """The fix must not over-exclude: other years stay in."""
    summary, daily = _minimal_corpus()
    _write_standings(standings_dir, [
        {"tournament_name": "Kingsisland Open", "year": 2024, "total_players": 480},
        {"tournament_name": "Kingsisland Open", "year": 2026, "total_players": 500},
    ])

    m = N5v4_Final()
    m.fit(summary, daily, verbose_standings_join=False,
          exclude_family_years={("Kings Island Open", 2026)})

    # 2024 survives, so the family is present and anchored on that row alone.
    assert m.family_mean_final.get("Kings Island Open") == 480


def test_unmapped_names_are_unaffected(standings_dir):
    summary, daily = _minimal_corpus()
    _write_standings(standings_dir, [
        {"tournament_name": "Southern Open", "year": 2026, "total_players": 210},
    ])

    m = N5v4_Final()
    m.fit(summary, daily, verbose_standings_join=False,
          exclude_family_years={("Southern Open", 2026)})

    assert "Southern Open" not in m.family_mean_final


def test_a_nan_year_does_not_kill_the_fit(standings_dir):
    """int(NaN) raised inside the apply and took the whole fit down."""
    summary, daily = _minimal_corpus()
    _write_standings(standings_dir, [
        {"tournament_name": "Kingsisland Open", "year": None, "total_players": 500},
    ])

    m = N5v4_Final()
    m.fit(summary, daily, verbose_standings_join=False,
          exclude_family_years={("Kings Island Open", 2026)})

    # Unparseable year cannot match an exclusion, so the row is kept.
    assert m.family_mean_final.get("Kings Island Open") == 500


def test_the_mapping_actually_renames_things():
    """Guards the premise: if no name differed, P1-2 would be untestable."""
    differing = [k for k, v in STANDINGS_NAME_MAP.items() if k != v]
    assert len(differing) > 20
    assert STANDINGS_NAME_MAP.get("Kingsisland Open") == "Kings Island Open"


# ── P1-3: recalibration state survives a raising predict_nowcast ────────────

class _Boom(Exception):
    pass


def _recal_corpus(n=5):
    """n completed tournaments with curve points at T=28 and T=14."""
    completed = _summary([
        {"tid": f"r{i}", "family": "Anchor Open", "final_count": 200 + i,
         "tournament_year": 2026, "last_reg": f"2026-0{(i % 9) + 1}-01"}
        for i in range(n)
    ])
    daily = pd.DataFrame([
        {"tid": f"r{i}", "T": T, "cum_regs": 150 + i}
        for i in range(n) for T in (28, 14)
    ])
    return completed, daily


def test_partial_results_survive_a_raising_predict_nowcast():
    """The stash/restore around predict_nowcast needs a finally.

    Note on severity: no caller wraps recalibrate() in try/except today, so the
    exception propagates and fails the pipeline step loudly rather than
    silently disabling anything. What the finally protects is the invariant —
    an exception must not leave the model holding the temporary blank instead
    of the corrections already fitted for earlier T points.
    """
    m = N5v4_Final()
    m._fit_tids = set()

    calls = {"n": 0}

    def flaky(count_at_T, T, family, **kw):
        calls["n"] += 1
        if T == 14:
            raise _Boom("simulated prediction failure at T=14")
        return (210, 190, 240)

    m.predict_nowcast = flaky
    completed, daily = _recal_corpus()

    with pytest.raises(_Boom):
        m.recalibrate(completed, daily, T_points=[28, 14], loo=False)

    assert 28 in m._recal_bias, (
        "the T=28 correction fitted before the failure was discarded; the model "
        "was left holding the temporary blank")
    assert 28 in m._recal_ci


def test_normal_path_still_fits_every_horizon():
    """The finally must not change non-raising behaviour."""
    m = N5v4_Final()
    m._fit_tids = set()
    m.predict_nowcast = lambda count_at_T, T, family, **kw: (210, 190, 240)
    completed, daily = _recal_corpus()

    diag = m.recalibrate(completed, daily, T_points=[28, 14], loo=False)

    assert set(diag) == {28, 14}
    assert set(m._recal_bias) == {28, 14}
    assert all(0.8 <= v <= 1.2 for v in m._recal_bias.values())


# ── P1-6: BLITZ_FAMILIES is per-instance ───────────────────────────────────

def test_blitz_families_do_not_leak_between_instances():
    baseline = set(N5v4_Final.BLITZ_FAMILIES)
    a, b = N5v4_Final(), N5v4_Final()

    a.BLITZ_FAMILIES.add("Synthetic Corpus Blitz")

    assert "Synthetic Corpus Blitz" not in b.BLITZ_FAMILIES
    assert "Synthetic Corpus Blitz" not in N5v4_Final.BLITZ_FAMILIES
    assert N5v4_Final.BLITZ_FAMILIES == baseline


def test_fit_populates_only_its_own_instance(standings_dir):
    baseline = set(N5v4_Final.BLITZ_FAMILIES)
    summary, daily = _minimal_corpus()
    summary.loc[len(summary)] = {
        "tid": "blz", "family": "Synthetic Rapid Championship", "final_count": 120,
        "tournament_year": 2024, "has_timestamps": True,
        "is_online": False, "is_covid": False, "last_reg": "2024-06-01",
    }

    a = N5v4_Final()
    a.fit(summary, daily, verbose_standings_join=False)
    b = N5v4_Final()

    assert "Synthetic Rapid Championship" in a.BLITZ_FAMILIES
    assert "Synthetic Rapid Championship" not in b.BLITZ_FAMILIES
    assert N5v4_Final.BLITZ_FAMILIES == baseline


# ── P1-5: the Compare tab reads fields the payload actually has ─────────────

COMPARE_JS = os.path.join(PROJECT_DIR, "docs", "tab_compare.js")
PAYLOAD = os.path.join(PROJECT_DIR, "docs", "data", "website_data.json")

# Fields the renderer derives or the row builder supplies rather than reading
# straight off a tournament card.
_NOT_PAYLOAD_FIELDS = {"t", "length", "reduce", "count"}


def _tournament_cards():
    with open(PAYLOAD) as f:
        data = json.load(f)
    cards = data.get("tournaments") if isinstance(data, dict) else None
    assert cards, "website_data.json has no tournaments array"
    return cards


def test_compare_tab_reads_only_fields_the_payload_supplies():
    """Catches the whole class, not just event_date.

    A stat row referencing a field that does not exist renders the '—'
    placeholder, which is indistinguishable from genuinely missing data.
    """
    src = open(COMPARE_JS).read()
    # The stat-row table: `{ label: '...', fn: t => ... }`
    block = re.search(r"const rows = \[(.*?)\n    \];", src, re.S)
    assert block, "could not locate the Compare tab stat-row table"
    referenced = set(re.findall(r"\bt\.([A-Za-z_][A-Za-z0-9_]*)", block.group(1)))
    referenced -= _NOT_PAYLOAD_FIELDS
    assert referenced, "no tournament fields found — did the block move?"

    available = set()
    for card in _tournament_cards():
        available.update(card.keys())

    missing = sorted(referenced - available)
    assert missing == [], (
        f"Compare tab reads field(s) absent from website_data.json: {missing}")


def test_event_date_is_not_referenced_anywhere_in_the_site():
    """The payload calls it event_start; event_date never existed."""
    offenders = []
    docs = os.path.join(PROJECT_DIR, "docs")
    for name in sorted(os.listdir(docs)):
        if not name.endswith(".js"):
            continue
        text = open(os.path.join(docs, name)).read()
        if re.search(r"\.event_date\b", text):
            offenders.append(name)
    assert offenders == [], f"stale event_date reference in: {offenders}"


# ── P1-1 / P1-7 / P1-8: the site must not assert numbers it has not measured ─

INDEX_HTML = os.path.join(PROJECT_DIR, "docs", "index.html")
ABOUT_JS = os.path.join(PROJECT_DIR, "docs", "tab_about.js")
GRID_JS = os.path.join(PROJECT_DIR, "docs", "panels_grid.js")
PERF_JS = os.path.join(PROJECT_DIR, "docs", "tab_performance.js")
HERO_JS = os.path.join(PROJECT_DIR, "docs", "hero_kpi.js")


def test_likely_range_tooltip_is_not_a_hardcoded_claim():
    """It asserted "8 times out of 10" while measured coverage was ~75%."""
    html = open(INDEX_HTML).read()
    th = re.search(r'<th[^>]*id="thLikelyRange"[^>]*>', html)
    assert th, "the Likely Range header lost its id"
    assert "out of 10" not in th.group(0), (
        "the Likely Range tooltip states a coverage rate as static markup")
    assert "thLikelyRange" in open(GRID_JS).read(), (
        "nothing sets the Likely Range tooltip from PERFORMANCE_DATA")


def test_coverage_tile_turns_green_only_at_the_advertised_target():
    """Green used to start at 75, below the 80% the site advertises."""
    src = open(PERF_JS).read()
    m = re.search(r"l: 'CI Coverage'.*?c: avgCov >= (\d+)", src, re.S)
    assert m, "could not find the CI Coverage tile threshold"
    assert int(m.group(1)) >= 80, (
        f"coverage tile reads green at {m.group(1)}%, under the 80% target")


def test_about_stat_chips_are_all_pipeline_sourced():
    """Three of the four were static markup; one had drifted 3x."""
    html = open(INDEX_HTML).read()
    about = re.search(r'<div class="stat-chip-row">(.*?)</div>\s*</div>\s*</div>',
                      html, re.S)
    assert about, "could not locate the About-panel stat-chip row"
    chips = re.findall(r'<div class="stat-chip-num[^"]*"([^>]*)>([^<]*)<', about.group(1))
    assert chips, "no stat chips found"

    about_js = open(ABOUT_JS).read()
    for attrs, value in chips:
        idm = re.search(r'id="([^"]+)"', attrs)
        assert idm, f"stat chip with value {value!r} has no id, so nothing can set it"
        chip_id = idm.group(1)
        assert chip_id in about_js, f"chip {chip_id} is never written by tab_about.js"
        # The markup value must be an inert placeholder, not a claim.
        assert not re.search(r"\d", value), (
            f"chip {chip_id} hardcodes {value!r}; it will drift from the regrade")


def test_hero_number_is_not_inside_a_live_region():
    """A live region around a 600ms rAF tween announces every frame."""
    html = open(INDEX_HTML).read()
    hero = re.search(r'<div class="hero" id="heroSection"([^>]*)>', html)
    assert hero, "hero container not found"
    assert "aria-live" not in hero.group(1), (
        "the hero container is a live region wrapping the animated number")

    num = re.search(r'id="heroNumber"([^>]*)>', html)
    assert num and 'aria-hidden="true"' in num.group(1), (
        "#heroNumber is tweened and must be hidden from assistive tech")

    ann = re.search(r'id="heroAnnounce"([^>]*)>', html)
    assert ann, "no dedicated announcement region for the hero value"
    assert "aria-live" in ann.group(1)
    assert "heroAnnounce" in open(HERO_JS).read(), (
        "nothing announces the final hero value")
