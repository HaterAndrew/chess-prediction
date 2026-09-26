"""Script loading order is what keeps Chart.js ahead of the app.

The 2026-09 refresh bug: the app scripts were classic (blocking) tags at the
end of <body> while Chart.js was a deferred CDN tag in <head>. Deferred scripts
run after parsing, so on a cold visit app.js ran init() before Chart existed,
renderChart threw, hideSkeletons() never ran, and the page sat on the skeleton
until a reload found Chart.js in cache. The fix is `defer` on every same-origin
script: deferred scripts execute in document order, and the chart tags come
first. These tests keep that shape from regressing one tag at a time.
"""
import os
import re

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
INDEX = os.path.join(DOCS, "index.html")
AUDIT_JS = os.path.join(DOCS, "audit.js")
BOOT_JS = os.path.join(DOCS, "boot.js")
SW_JS = os.path.join(DOCS, "sw.js")

SCRIPT_TAG = re.compile(r"<script\b([^>]*)>", re.I)
SRC_ATTR = re.compile(r'\bsrc="([^"]+)"')


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _script_tags(html):
    """(attribute string, src) for every <script> with a src, in document order."""
    out = []
    for m in SCRIPT_TAG.finditer(html):
        attrs = m.group(1)
        src = SRC_ATTR.search(attrs)
        if src:
            out.append((attrs, src.group(1)))
    return out


def _is_same_origin(src):
    return not re.match(r"^(https?:)?//", src)


def test_every_same_origin_script_except_boot_is_deferred():
    tags = _script_tags(_read(INDEX))
    same_origin = [(a, s) for a, s in tags if _is_same_origin(s)]
    assert same_origin, "no same-origin script tags found in index.html"
    for attrs, src in same_origin:
        name = src.split("?")[0]
        if name == "boot.js":
            # boot.js is the one blocking head script: it must run before first
            # paint (service-worker bootstrap, and later the theme attribute).
            assert " defer" not in attrs, "boot.js must stay a blocking head script"
            continue
        assert re.search(r"\bdefer\b", attrs), (
            f"{src} is loaded without `defer`; a classic tag runs before the "
            f"deferred Chart.js and reintroduces the cold-load race")


def test_chart_library_tags_precede_every_app_script():
    tags = _script_tags(_read(INDEX))
    srcs = [s for _, s in tags]
    chart = next(i for i, s in enumerate(srcs) if "chart.umd" in s)
    adapter = next(i for i, s in enumerate(srcs) if "chartjs-adapter" in s)
    first_app = next(i for i, s in enumerate(srcs)
                     if _is_same_origin(s) and not s.startswith("boot.js"))
    assert chart < first_app and adapter < first_app, (
        "Chart.js and its adapter must come before the first app script so "
        "defer order makes Chart available to init()")
    for i in (chart, adapter):
        assert re.search(r"\bdefer\b", tags[i][0]), f"{srcs[i]} must be deferred"


def test_exceljs_is_not_loaded_on_every_page_view():
    srcs = [s for _, s in _script_tags(_read(INDEX))]
    assert not any("exceljs" in s.lower() for s in srcs), (
        "exceljs is back as a script tag in index.html; audit.js loads it on "
        "demand via loadExcelJS")


def test_exceljs_lazy_loader_matches_the_service_worker_allowlist():
    """The on-demand URL and its SRI hash must be the ones sw.js serves cache-first."""
    audit = _read(AUDIT_JS)
    src = re.search(r"const EXCELJS_SRC = '([^']+)'", audit)
    sri = re.search(r"const EXCELJS_SRI = '([^']+)'", audit)
    assert src and sri, "audit.js must define EXCELJS_SRC and EXCELJS_SRI"
    assert sri.group(1).startswith("sha384-"), "the SRI hash must be sha384"
    assert src.group(1) in _read(SW_JS), (
        "sw.js CDN_ASSETS no longer lists the exceljs URL audit.js fetches; "
        "a repeat export would go to the network instead of the cache")
    assert "s.integrity = EXCELJS_SRI" in audit and "s.crossOrigin = 'anonymous'" in audit, (
        "the injected script tag must carry the SRI hash and crossorigin, like the old tag did")


def test_boot_registers_the_service_worker_after_load():
    """boot.js is the only blocking script; its job is the SW bootstrap.

    Registration waits for the window `load` event: registering at parse time
    started the worker's install precache while the page was still fetching
    its own scripts, and the two competed for bandwidth on the cold visit.
    """
    boot = _read(BOOT_JS)
    assert re.search(
        r"addEventListener\('load',[\s\S]*?serviceWorker\.register\('sw\.js'\)", boot), (
        "boot.js must register sw.js inside a window 'load' listener")


def test_the_github_io_redirect_waits_for_the_cutover():
    """boot.js sends github.io visits to chessentries.com only once the domain
    answers; until the cutover PR flips the flag, the Pages copy keeps serving."""
    boot = _read(BOOT_JS)
    assert "var CUTOVER = false;" in boot, "the github.io redirect must stay off until the cutover"
    assert re.search(r"if \(CUTOVER && ", boot), "the redirect must be gated on CUTOVER"


def test_the_pages_copy_keeps_its_worker_until_the_cutover():
    """Pages serves no /ask or /cca-entrylist, so the github.io copy keeps
    calling the Worker it always used, and the CSP still admits that host."""
    legacy = "https://chess-ask.hater-andrewd.workers.dev"
    for name in ("tab_ask.js", "audit.js"):
        src = _read(os.path.join(DOCS, name))
        assert re.search(r"github\\.io\$/\.test\(l\.hostname\)\) return '" + re.escape(legacy), src), (
            f"{name} must fall back to the legacy Worker on github.io")
    html = _read(os.path.join(DOCS, "index.html"))
    csp = re.search(r'Content-Security-Policy["\']\s+content="([^"]+)"', html).group(1)
    connect = [d for d in csp.split(";") if d.strip().startswith("connect-src")][0]
    assert legacy in connect, "the CSP connect-src must keep the legacy Worker until the cutover"
