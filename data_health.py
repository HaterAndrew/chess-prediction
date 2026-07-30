"""
data_health.py — Health scan of the prediction OUTPUT (website_data.json).

Audits every tournament card for the degradation modes that produced the
World Open Under 13 / Eastern (in CT/NJ) bugs and adjacent issues. Read-only:
loads output/website_data.json and cross-references the input CSVs, ranks
findings by severity, and writes a markdown report + JSON summary.

Existing tools validate the INPUTS (validate_scraped_data.py) or operational
run health (scrape_health.py); nothing audited the per-tournament prediction
cards until now. Family-name folding reuses tournament_aliases so the scan
agrees with the pipeline on what counts as the same tournament.

CRITICAL/HIGH findings are printed as `WARNING: data-health ...` lines so that
auto_update._harvest_warnings folds them into output/audit_warnings.json with
no extra wiring.

Usage:
    python3 data_health.py            # scan, write reports, exit 0
    python3 data_health.py --strict   # exit 1 if any CRITICAL finding
"""

import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
from tournament_aliases import (  # noqa: E402
    canonicalize_family,
    is_wo_excluded,
)

OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
WEBSITE_JSON = os.path.join(OUTPUT_DIR, "website_data.json")
DAILY_SCRAPE_CSV = os.path.join(OUTPUT_DIR, "daily_scrape.csv")
SUMMARY_CSV = os.path.join(OUTPUT_DIR, "tournament_summary.csv")
METADATA_CSV = os.path.join(OUTPUT_DIR, "tournament_metadata.csv")
PERFORMANCE_JSON = os.path.join(OUTPUT_DIR, "performance_data.json")
UPDATE_LOG_CSV = os.path.join(OUTPUT_DIR, "update_log.csv")
HEALTH_JSON = os.path.join(OUTPUT_DIR, "data_health.json")
AUDIT_DIR = os.path.join(PROJECT_DIR, "audit", "data-health")

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "INFO"]

# Gap (in days) between the last two chart points that counts as "large" for the
# daily-large-recent-gap early warning (v3 Q3). A scrape runs nightly, so a gap
# beyond a long weekend means scrape days were missed.
DAILY_GAP_WARN_DAYS = 4

# Graded curve peak below this fraction of the final count means the curve is
# frozen relative to a reconcile-bumped final (v3 Q2). Matches
# 04e_performance_data.FROZEN_CURVE_MIN_RATIO — kept as a separate constant so
# the scanner still reports if the two ever drift apart.
PERF_FROZEN_CURVE_RATIO = 0.60

# Fraction of scraped entries withdrawn that is worth flagging. The published
# count is gross by design (H13), so this gap never shows on the page.
#
# Measured before being set, not guessed: on the 2026-07-25 corpus 12 of 30
# scraped events carry withdrawals, spanning 0.5% (Bradley, 1 of 207) to 7.6%
# (Pittsburgh, 13 of 170). 0.10 therefore sits just above the observed ceiling
# and fires on none of them today, which is what an early warning should do —
# silent on healthy data, loud on a real change. Re-measure before moving it.
WITHDRAWAL_GAP_WARN_FRAC = 0.10

# Side events that are intentionally not predicted as standalone tournaments.
_BLITZ_RE = re.compile(r"Blitz|Rapid|Bullet|Bughouse|Armageddon", re.IGNORECASE)


def _canon(name):
    return canonicalize_family(name) if isinstance(name, str) else name


def _strip_year(name):
    if isinstance(name, str) and name.startswith("2026 "):
        return name[5:]
    return name


class HealthReport:
    """Severity-tiered findings over the prediction output.

    Modeled on validate_scraped_data.ValidationReport, but ranks findings into
    CRITICAL / HIGH / MEDIUM / INFO instead of a binary error/warning split.
    """

    def __init__(self, generated=None):
        self.generated = generated
        self.findings = []  # list of dicts: severity, mode, family, message

    def add(self, severity, mode, family, message):
        assert severity in SEVERITIES, severity
        self.findings.append({
            "severity": severity,
            "mode": mode,
            "family": family,
            "message": message,
        })

    def by_severity(self, severity):
        return [f for f in self.findings if f["severity"] == severity]

    def counts(self):
        return {s: len(self.by_severity(s)) for s in SEVERITIES}

    def has_critical(self):
        return any(f["severity"] == "CRITICAL" for f in self.findings)

    def summary(self):
        """Human-readable grouped summary for stdout."""
        c = self.counts()
        lines = [
            "",
            "=" * 66,
            f"  DATA HEALTH SCAN — generated {self.generated}",
            "=" * 66,
            "  " + "   ".join(f"{s}: {c[s]}" for s in SEVERITIES),
        ]
        for sev in SEVERITIES:
            items = self.by_severity(sev)
            if not items:
                continue
            lines.append(f"\n  {sev} ({len(items)}):")
            for f in items:
                lines.append(f"    [{f['mode']}] {f['family']}: {f['message']}")
        lines.append("")
        return "\n".join(lines)

    def warning_lines(self):
        """`WARNING:`-prefixed lines for CRITICAL/HIGH so auto_update harvests
        them into audit_warnings.json. MEDIUM findings surface as ONE
        aggregate pointer line (v5 Cat V — the standing null-fee set sat
        invisible in the JSON report for months because this channel dropped
        MEDIUM entirely); INFO stays in the report only."""
        out = []
        for sev in ("CRITICAL", "HIGH"):
            for f in self.by_severity(sev):
                out.append(
                    f"WARNING: data-health [{sev}] {f['mode']} — "
                    f"{f['family']}: {f['message']}"
                )
        n_medium = len(self.by_severity("MEDIUM"))
        if n_medium:
            out.append(
                f"WARNING: data-health: {n_medium} MEDIUM finding(s) — "
                f"see output/data_health.json"
            )
        return out

    def to_json(self):
        return {
            "generated": self.generated,
            "scanned_at": datetime.now().isoformat(timespec="seconds"),
            "counts": self.counts(),
            "findings": self.findings,
        }

    def to_markdown(self):
        c = self.counts()
        lines = [
            f"# Tournament Data-Health Scan — {self.generated}",
            "",
            f"Scanned {datetime.now().strftime('%Y-%m-%d %H:%M')}. "
            + " · ".join(f"**{s}** {c[s]}" for s in SEVERITIES),
            "",
        ]
        for sev in SEVERITIES:
            items = self.by_severity(sev)
            if not items:
                continue
            lines.append(f"## {sev} ({len(items)})")
            lines.append("")
            lines.append("| Mode | Tournament | Finding |")
            lines.append("|---|---|---|")
            for f in items:
                fam = f["family"].replace("|", "\\|")
                msg = f["message"].replace("|", "\\|")
                lines.append(f"| {f['mode']} | {fam} | {msg} |")
            lines.append("")
        return "\n".join(lines)


# ── Context: cross-reference lookups built once from the input CSVs ──────────

class Context:
    def __init__(self):
        self.scrape_latest = self._load_scrape_latest()
        self.summary_2026 = self._load_2026_families(SUMMARY_CSV, "tournament_year")
        self.metadata_2026 = self._load_2026_families(METADATA_CSV, "year")
        self.log_hist = self._load_log_history()
        self.perf_finals = self._load_performance_finals()

    def _load_performance_finals(self):
        """canon_family -> {'final_count', 'peak_count_at_T'} from the graded set.

        v3 Q2: data_health never loaded performance_data.json, so the frozen-curve
        corruption behind the wrong-low public grade (T1/R2) had no health or test
        coverage anywhere. Loading it lets the scanner cross-check the numbers the
        grade was computed from against the ones the site publishes.
        """
        out = {}
        if not os.path.exists(PERFORMANCE_JSON):
            return out
        try:
            with open(PERFORMANCE_JSON) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return out
        for t in data.get("tournaments") or []:
            preds = t.get("predictions") or []
            counts = [p.get("count_at_T") for p in preds
                      if isinstance(p.get("count_at_T"), int)]
            out[_canon(t.get("family", ""))] = {
                "final_count": t.get("final_count"),
                "peak_count_at_T": max(counts) if counts else None,
            }
        return out

    def _load_scrape_latest(self):
        """canon_family -> {'net', 'gross', 'date'} from the most recent scrape."""
        latest = {}
        if not os.path.exists(DAILY_SCRAPE_CSV):
            return latest
        with open(DAILY_SCRAPE_CSV, newline="") as fh:
            for row in csv.DictReader(fh):
                fam = _canon(_strip_year(row.get("tournament_name", "")))
                date = row.get("date", "")
                try:
                    entry = int(float(row.get("entry_count") or 0))
                except ValueError:
                    entry = 0
                active_raw = row.get("active_count")
                try:
                    active = int(float(active_raw)) if active_raw not in (None, "") else entry
                except ValueError:
                    active = entry
                net = active if active > 0 else entry
                cur = latest.get(fam)
                if cur is None or date >= cur["date"]:
                    latest[fam] = {"net": net, "gross": entry, "date": date}
        return latest

    def _load_2026_families(self, path, year_col):
        fams = set()
        if not os.path.exists(path):
            return fams
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                yr = str(row.get(year_col, "")).strip()
                if yr.startswith("2026"):
                    fams.add(_canon(row.get("family", "")))
        return fams

    def _load_log_history(self):
        """canon_family -> ordered list of (point_estimate, current_count) for
        live rows, used to detect an estimate frozen while entries rise."""
        hist = defaultdict(list)
        if not os.path.exists(UPDATE_LOG_CSV):
            return hist
        with open(UPDATE_LOG_CSV, newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("status") != "live":
                    continue
                fam = _canon(row.get("family", ""))
                try:
                    pe = int(float(row.get("point_estimate") or 0))
                    cc = int(float(row.get("current_count") or 0))
                except ValueError:
                    continue
                hist[fam].append((pe, cc))
        return hist


# ── Card classification helpers ─────────────────────────────────────────────

def _is_roster_pending(t):
    return t.get("prediction_tier") == "roster-pending"


def _is_main_path(t):
    # v5 Cat R: roster-pending cards served by the MODEL are live predictions
    # and must move nightly — watch them like any main-path card. Only the
    # metadata_* interim cards keep the frozen-estimate exemption (those are
    # expected to sit still between metadata refreshes).
    if t.get("status") not in ("live", "complete"):
        return False
    return not _is_roster_pending(t) or t.get("prediction_source") == "model"


def _hist_counts(t):
    return [h.get("count") for h in (t.get("historical") or []) if h.get("count") is not None]


# ── Checks (full ranked catalog) ────────────────────────────────────────────

def scan(data, ctx):
    report = HealthReport(generated=data.get("generated"))
    tournaments = data.get("tournaments", [])
    live_complete = [t for t in tournaments if t.get("status") in ("live", "complete", "not_tracked")]

    # canon families that appear as any 2026 card, and canon families that have
    # historical editions (for name-mismatch + dropped-event detection).
    card_canon_2026 = {_canon(t["family"]) for t in tournaments if t.get("year") == 2026}
    hist_canon = {_canon(t["family"]) for t in tournaments if t.get("status") == "historical"}

    # ---- CRITICAL ----------------------------------------------------------

    # Mode 12: scraped >=10 entries but no 2026 card at all (silently dropped).
    for fam, info in ctx.scrape_latest.items():
        if info["gross"] < 10:
            continue
        if not fam or is_wo_excluded(fam) or _BLITZ_RE.search(fam):
            continue
        if fam not in card_canon_2026:
            report.add("CRITICAL", "dropped-event", fam,
                       f"scraped {info['gross']} entries on {info['date']} but no 2026 card in output")

    for t in live_complete:
        fam = t.get("family", "?")
        src = t.get("prediction_source")
        pe = t.get("point_estimate")
        cc = t.get("current_count")
        # Mode 7b: model predicts fewer than already registered.
        if (t.get("status") == "live" and src not in ("live_scrape", "final", None)
                and isinstance(pe, int) and isinstance(cc, int) and cc > pe):
            report.add("CRITICAL", "count-exceeds-estimate", fam,
                       f"current_count {cc} > point_estimate {pe} ({src})")

    # Mode 1b: a MAIN-PATH live card frozen on one estimate across runs while
    # entries climbed — the World Open U13 shape. Covers model-served cards
    # including admitted roster-pending ones (v5 Cat R); only metadata_*
    # interim cards are expected to sit still between metadata refreshes.
    for t in live_complete:
        if t.get("status") != "live" or not _is_main_path(t):
            continue
        seq = ctx.log_hist.get(_canon(t.get("family", "")), [])
        if len(seq) < 3:
            continue
        ests = {pe for pe, _ in seq}
        counts = [cc for _, cc in seq]
        if len(ests) == 1 and max(counts) > min(counts):
            report.add("CRITICAL", "frozen-estimate", t.get("family", "?"),
                       f"estimate stuck at {next(iter(ests))} across {len(seq)} runs "
                       f"while entries rose {min(counts)}->{max(counts)}")

    # Modes daily-*: chart-series integrity (v3 Q1/Q3, audit/AUDIT_2026-07-25.md).
    # The 2026-07-25 incident shipped a Bradley Open curve topping out at 625
    # against a real count of 197 and passed this scanner clean, because the only
    # daily_data check here was the single-point INFO stub below. These rules
    # mirror build_chart_series's post-build invariant so a misassembled curve is
    # caught at commit time instead of on the public site.
    for t in live_complete:
        fam = t.get("family", "?")
        series = t.get("daily_data") or []
        pts = [p for p in series if isinstance(p, (list, tuple)) and len(p) >= 2]
        if not pts:
            continue
        counts = [p[1] for p in pts]
        days = [p[0] for p in pts]

        # A live card's cumulative curve can never exceed the entries scraped.
        cc = t.get("current_count")
        if t.get("status") == "live" and isinstance(cc, int) and max(counts) > cc:
            report.add("CRITICAL", "daily-max-exceeds-count", fam,
                       f"daily_data max {max(counts)} > current_count {cc} "
                       f"— chart series is misanchored")

        # Cumulative totals cannot fall.
        drops = [(days[i - 1], counts[i - 1], days[i], counts[i])
                 for i in range(1, len(counts)) if counts[i] < counts[i - 1]]
        if drops:
            d0, c0, d1, c1 = drops[0]
            report.add("HIGH", "daily-non-monotone", fam,
                       f"cumulative count falls {c0}->{c1} between day {d0} and "
                       f"{d1} ({len(drops)} drop(s))")

        # Day indices must be unique and non-negative.
        if len(set(days)) != len(days) or any(d < 0 for d in days):
            report.add("HIGH", "daily-dup-neg-index", fam,
                       f"day indices not unique/non-negative: {days[:12]}")

        # Q3: a large gap immediately before the tail is the precondition that let
        # the A4 rescale fire. Surface it before it corrupts a curve.
        if len(days) >= 2:
            tail_gap = days[-1] - days[-2]
            if tail_gap > DAILY_GAP_WARN_DAYS:
                report.add("MEDIUM", "daily-large-recent-gap", fam,
                           f"{tail_gap}-day gap before the final chart point "
                           f"(day {days[-2]} -> {days[-1]})")

    # Mode performance-frozen-curve (v3 Q2): an event whose graded curve tops out
    # far below the final it was graded against. The model is then scored on the
    # gap between a stale export and a reconcile-bumped final rather than on its
    # own error — this is what pushed the published headline grade to D when the
    # model had earned a C. 04e now excludes these from grading; this rule makes
    # sure a new one cannot appear unnoticed.
    for fam, info in (getattr(ctx, "perf_finals", None) or {}).items():
        final = info.get("final_count")
        peak = info.get("peak_count_at_T")
        if not isinstance(final, int) or final <= 0 or not isinstance(peak, int):
            continue
        ratio = peak / final
        if ratio < PERF_FROZEN_CURVE_RATIO:
            report.add("HIGH", "performance-frozen-curve", fam,
                       f"graded curve peaks at {round(ratio*100)}% of its {final} final "
                       f"(peak count_at_T={peak}) — stale export, not a model miss")

    # ---- HIGH --------------------------------------------------------------

    # Mode 9a: two live/complete cards collapse to the same canonical family+year.
    by_canon_year = defaultdict(list)
    for t in live_complete:
        by_canon_year[(_canon(t.get("family", "")), t.get("year"))].append(t.get("family"))
    for (cfam, yr), names in by_canon_year.items():
        if len(names) > 1:
            report.add("HIGH", "name-variant-split", cfam,
                       f"{len(names)} cards share canonical family for {yr}: {sorted(set(names))}")

    for t in live_complete:
        fam = t.get("family", "?")
        hc = _hist_counts(t)
        nhe = t.get("n_historical_editions")
        tier = t.get("prediction_tier")

        # Mode 3b: live card with empty history despite same-name historical
        # editions existing (a name fold that didn't happen).
        if (t.get("status") == "live" and not hc and not _is_roster_pending(t)
                and _canon(fam) in hist_canon):
            report.add("HIGH", "empty-history-name-mismatch", fam,
                       "live card has no historical[] but historical editions exist under this family")

        # Mode 11/3c: alias family reported with 0 editions (and so wrongly
        # low-confidence) despite a populated historical[].
        if tier == "family-alias" and nhe == 0 and hc:
            report.add("HIGH", "alias-n-editions-mislabel", fam,
                       f"prediction_tier=family-alias but n_historical_editions=0 "
                       f"with {len(hc)} historical editions present")

        # Mode 6: card count drifted from the latest scrape.
        #
        # Compare gross to gross. `current_count` is the GROSS row count — that
        # is the published semantic, settled in H13 so the cards, the perf tab
        # and the grader all quote one number. Checking it against the scrape's
        # NET count made every event with even one withdrawal fail: nine HIGH
        # findings on a healthy run, all of them measuring the withdrawal rate
        # rather than any staleness. A rule that fires on every healthy run
        # teaches people to skip the whole report, which costs more than the
        # rule was ever worth.
        #
        # The net/gross gap is worth surfacing, but it is a different fact and
        # is reported below at its own severity.
        if t.get("status") in ("live", "complete"):
            sl = ctx.scrape_latest.get(_canon(fam))
            cc = t.get("current_count")
            if sl is not None and isinstance(cc, int) and cc != sl["gross"]:
                report.add("HIGH", "stale-count", fam,
                           f"current_count {cc} != latest scrape gross "
                           f"{sl['gross']} ({sl['date']})")

    # ---- MEDIUM ------------------------------------------------------------

    for t in live_complete:
        fam = t.get("family", "?")
        hc = _hist_counts(t)
        nhe = t.get("n_historical_editions")
        pe, lo, hi = t.get("point_estimate"), t.get("ci_lower"), t.get("ci_upper")

        # Mode 5b: sparse history but NOT flagged low-confidence (hiding it).
        if t.get("low_confidence") is False and isinstance(nhe, int) and nhe < 4:
            report.add("MEDIUM", "sparse-history-hidden", fam,
                       f"n_historical_editions={nhe} but low_confidence=False")

        # Mode 4a/5c: pure no-history default guess.
        if pe == 100 and lo == 70 and hi == 130 and not hc:
            report.add("MEDIUM", "no-history-default", fam,
                       "point_estimate=100 / CI 70-130 with no historical editions")

        # An unusually large withdrawal rate. The cards publish gross counts by
        # design (H13), so a wide net/gross gap never shows on the page — but a
        # tenth of the field withdrawing is worth a look, whether it is real
        # attrition or a double-counted export.
        #
        # This is the signal the old stale-count rule was accidentally emitting,
        # separated out and given a threshold. At >0 it fired on nearly every
        # event and meant nothing.
        sl = ctx.scrape_latest.get(_canon(fam))
        if sl and sl["gross"] > 0:
            gap = sl["gross"] - sl["net"]
            if gap > 0 and gap / sl["gross"] > WITHDRAWAL_GAP_WARN_FRAC:
                report.add("MEDIUM", "large-withdrawal-gap", fam,
                           f"{gap} of {sl['gross']} scraped entries withdrawn "
                           f"({gap / sl['gross'] * 100:.0f}%) as of {sl['date']}")

        if t.get("status") == "live":
            # Mode 8a: fee unknown for a near event.
            dr = t.get("days_remaining")
            if t.get("regular_fee") is None and isinstance(dr, int) and dr < 30:
                report.add("MEDIUM", "null-fee-near-event", fam,
                           f"regular_fee is null with {dr} days remaining")
            # Mode 8b/8c: missing event dates distort the countdown/status.
            if t.get("event_start") is None:
                report.add("MEDIUM", "null-event-start", fam, "event_start is null on a live card")
            if t.get("event_end") is None:
                report.add("MEDIUM", "null-event-end", fam, "event_end is null on a live card")
            # Mode 8d: main-path live card missing registration_close.
            if not _is_roster_pending(t) and not t.get("registration_close"):
                report.add("MEDIUM", "missing-registration-close", fam,
                           "main-path live card has no registration_close")

    # ---- INFO (high-volume modes aggregated to avoid flooding) -------------

    roster_pending = sorted({t.get("family") for t in tournaments if _is_roster_pending(t)})
    for fam in roster_pending:
        report.add("INFO", "roster-pending", fam,
                   "interim estimate — not in trained roster yet (pending fresh all_registrations.csv export)")

    no_curve = sum(
        1 for t in tournaments
        if t.get("status") == "historical"
        and (t.get("daily_data") or []) == [[0, t.get("current_count")]]
    )
    if no_curve:
        report.add("INFO", "historical-no-curve", f"{no_curve} cards",
                   "historical editions lack day-by-day registration data (no timestamps captured)")

    walkin_est = sum(1 for t in tournaments if t.get("walkin_source") == "estimate")
    if walkin_est:
        report.add("INFO", "walkin-global-fallback", f"{walkin_est} cards",
                   "walk-in multiplier used the global 'estimate' fallback (no family-specific stats)")

    return report


def load_website_data():
    if not os.path.exists(WEBSITE_JSON):
        raise SystemExit(f"ERROR: {WEBSITE_JSON} not found — run 04d_website_data_v2.py first")
    with open(WEBSITE_JSON) as fh:
        return json.load(fh)


def exit_code_for(report, strict, crashed=False):
    """Map a scan outcome to the process exit code (v5 Cat T).

    0: clean (or findings without --strict) · 3: --strict with a CRITICAL
    finding (the pipeline must abort and publish the degraded banner) ·
    4: the scanner itself crashed (telemetry loss, NOT a data verdict — the
    pipeline treats it as non-fatal so a scanner bug can't block publishing).
    Distinct codes because auto_update must tell "the data is bad" apart from
    "the scanner broke": the old blanket try/except treated both as ignorable,
    which silently defeated --strict.
    """
    if crashed:
        return 4
    if strict and report.has_critical():
        return 3
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    strict = "--strict" in argv

    data = load_website_data()
    ctx = Context()
    try:
        report = scan(data, ctx)
    except Exception as e:  # scanner bug — loud, but distinct from a finding
        print(f"WARNING: data-health scanner crashed: {e}")
        return exit_code_for(None, strict, crashed=True)

    # Markdown report
    os.makedirs(AUDIT_DIR, exist_ok=True)
    md_path = os.path.join(AUDIT_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.md")
    with open(md_path, "w") as fh:
        fh.write(report.to_markdown())

    # JSON summary
    with open(HEALTH_JSON, "w") as fh:
        json.dump(report.to_json(), fh, indent=2)

    # stdout: harvestable WARNING lines first, then the grouped summary
    for line in report.warning_lines():
        print(line)
    print(report.summary())
    print(f"  Report: {md_path}")
    print(f"  JSON:   {HEALTH_JSON}")

    return exit_code_for(report, strict)


if __name__ == "__main__":
    sys.exit(main())
