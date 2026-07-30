"""Finding container + report rendering (data_health, verbatim)."""
from datetime import datetime


SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "INFO"]


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

