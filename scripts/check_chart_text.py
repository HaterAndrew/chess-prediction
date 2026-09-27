"""Check that no chart text is covered: run after any chart change.

Loads the site in Chromium at 1440 and 390 in both themes, opens every view
and section that draws a chart, and reports each canvas label that overlaps
another label, is crossed by a line or mark without a halo under it, or is
drawn over afterwards (scripts/chart_text_probe.js records the draws).
Exits 1 on any finding.

    python3 scripts/check_chart_text.py http://127.0.0.1:8000/

Needs Playwright with Chromium (`pip install playwright && playwright
install chromium`); it is a development check, not part of the CI suite.
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

PROBE = (pathlib.Path(__file__).parent / "chart_text_probe.js").read_text()
SIZES = ((1440, 900, False), (390, 844, True))

# The page states that draw charts: (name, hash or JS picking a tournament).
STATES = (
    ("forecast", "#predictions/0"),
    ("forecast-far", "far"),
    ("forecast-done", "done"),
    ("performance", "#performance"),
    ("compare", "#compare"),
)
PICK = {
    "far": "TOURNAMENT_DATA.tournaments.findIndex(t => t.status === 'live' && t.days_remaining > 70)",
    "done": "TOURNAMENT_DATA.tournaments.findIndex(t => t.status === 'complete')",
}


def _open(pg, base, target):
    if target in PICK:
        pg.goto(base, wait_until="networkidle")
        i = pg.evaluate(PICK[target])
        if i < 0:
            return False
        target = f"#predictions/{i}"
    pg.goto(base + target, wait_until="networkidle")
    pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelectorAll('details.sect').forEach(d => d.open = true)")
    pg.wait_for_timeout(1500)
    return True


def main(base):
    findings = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in ("light", "dark"):
            for w, h, mobile in SIZES:
                ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=mobile,
                                          has_touch=mobile, device_scale_factor=2, reduced_motion="reduce")
                ctx.add_init_script(f"try {{ localStorage.setItem('cep:theme', '{theme}'); }} catch (e) {{}}")
                ctx.add_init_script(PROBE)
                pg = ctx.new_page()
                for name, target in STATES:
                    if not _open(pg, base, target):
                        continue
                    for canvas in pg.evaluate("window.__chartTextReport()"):
                        for problem in canvas["problems"]:
                            findings += 1
                            print(f"{theme} {w} {name} #{canvas['id']}: {problem}")
                ctx.close()
        browser.close()
    print(f"{findings} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"))
