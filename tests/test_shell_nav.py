"""The shell: one rail for every view, the bottom bar's pinned set, the More
sheet, the asset registries, and the markup hygiene the redesign set.

The 2026-09 shell replaced the tab strip and its "Other" overflow menu with
the registry's rail (a side rail on a desktop, a bottom bar on a phone) and
a Season view that took the portfolio blocks off the Forecast. Each rule
here is one that a later edit could break one attribute at a time without
any other test noticing: a view with no button is unreachable, a stylesheet
missing from the stamp list ships uncached, a glyph entity in the chrome is
a font-dependent icon.
"""
import os
import re
from pathlib import Path

from pipeline.stamping import STAMPED_DATA, STAMPED_SCRIPTS

DOCS = Path(__file__).resolve().parent.parent / "docs"
INDEX = DOCS / "index.html"
APP_JS = DOCS / "app.js"
SHELL_JS = DOCS / "shell.js"
ACTIONS_JS = DOCS / "actions.js"
SW_JS = DOCS / "sw.js"
SHELL_STYLESHEETS = ("shell.css", "controls.css", "overlays.css", "cards.css")

# AP style keeps these lowercase inside a title.
SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor",
               "of", "on", "or", "the", "to", "up", "yet"}


def _read(path):
    return path.read_text(encoding="utf-8")


def _rail(html):
    start = html.index('<aside id="rail"')
    return html[start:html.index("</aside>", start)]


def _topbar(html):
    start = html.index('<header class="topbar"')
    return html[start:html.index("</header>", start)]


def _js_list(src, name):
    m = re.search(rf"const {name} = \[(.*?)\];", src, re.S)
    assert m, f"{name} not found"
    return re.findall(r"'([a-z]+)'", m.group(1))


def _rail_buttons(html):
    """{tab: (label, pinned)} for every view button in the rail."""
    out = {}
    for m in re.finditer(r'<button[^>]*data-act="page-tab"[^>]*data-tab="([a-z]+)"([^>]*)>.*?<b>([^<]+)</b>',
                         _rail(html), re.S):
        out[m.group(1)] = (m.group(3), 'data-bar="pinned"' in m.group(2))
    return out


def _title_case(label):
    words = label.split()
    return all(w[0].isupper() or (i > 0 and w in SMALL_WORDS) for i, w in enumerate(words))


def test_every_view_has_a_rail_button_and_a_panel():
    html = _read(INDEX)
    views = _js_list(_read(APP_JS), "VALID_TABS")
    buttons = _rail_buttons(html)
    for tab in views:
        assert tab in buttons, f"no rail button for the {tab} view"
        assert f'id="ptab-{tab}"' in _rail(html), f"the {tab} button lost its id"
        assert f'id="panel-{tab}"' in html, f"no panel for the {tab} view"
    assert set(buttons) == set(views), "the rail lists a view the router does not know"


def test_swipe_order_lists_every_view_once():
    app = _read(APP_JS)
    order = _js_list(app, "PAGE_TAB_ORDER")
    assert sorted(order) == sorted(set(order)), "a view appears twice in PAGE_TAB_ORDER"
    assert set(order) == set(_js_list(app, "VALID_TABS"))


def test_the_bottom_bar_pins_four_views_and_more():
    html = _read(INDEX)
    pinned = {tab for tab, (_, p) in _rail_buttons(html).items() if p}
    assert pinned == {"predictions", "season", "performance", "ask"}, pinned
    assert re.search(r'<button[^>]*id="moreNav"[^>]*data-act="open-more-sheet"', _rail(html)), \
        "the bar's More button is missing or unwired"
    assert 'id="moreSheet"' in html and 'id="moreSheetList"' in html


def test_the_other_menu_is_gone():
    for path in (INDEX, APP_JS, ACTIONS_JS):
        text = _read(path)
        for relic in ("moreMenu", "page-tab-more", "more-tab", "toggle-more-menu", "MORE_MENU_TABS"):
            assert relic not in text, f"{relic} is back in {path.name}"


def test_view_titles_match_the_rail_labels_in_title_case():
    html = _read(INDEX)
    titles = dict(re.findall(r"^\s*([a-z]+): '([^']+)',", _read(SHELL_JS), re.M))
    for tab, (label, _) in _rail_buttons(html).items():
        assert titles.get(tab) == label, f"{tab}: rail says {label!r}, VIEW_TITLES says {titles.get(tab)!r}"
        assert _title_case(label), f"{label!r} is not in AP title case"
    assert _title_case("More")


def test_the_shell_markup_carries_no_glyph_entities():
    html = _read(INDEX)
    for name, chunk in (("top bar", _topbar(html)), ("rail", _rail(html))):
        found = re.findall(r"&#x?[0-9a-fA-F]+;", chunk)
        assert not found, f"{name} uses glyph entities {found}; icons are inline SVG"
    assert "♔" not in html and "&#9822;" not in html, "the emoji favicon or logo glyph is back"


def test_the_season_view_holds_the_portfolio_blocks():
    html = _read(INDEX)
    start = html.index('id="panel-season"')
    end = html.index('id="panel-', start + 1)
    season = html[start:end]
    for block in ('id="summaryBar"', 'id="calendarStrip"', 'id="miniGrid"', 'id="sect-table"', 'id="tourneyTable"'):
        assert block in season, f"{block} is not inside the Season view"
    forecast = html[html.index('id="panel-predictions"'):start]
    assert 'id="heroSection"' in forecast and 'id="mainChart"' in forecast


def test_the_markup_nests():
    """One extra </div> once closed <main> early, leaving every later view outside it."""
    html = re.sub(r"<!--.*?-->", "", _read(INDEX), flags=re.S)
    assert len(re.findall(r"<div\b", html)) == len(re.findall(r"</div>", html)), "unbalanced <div>"
    assert html.count("<main") == 1 and html.count("</main>") == 1
    main_start, main_end = html.index("<main"), html.index("</main>")
    for panel in ("panel-predictions", "panel-season", "panel-ask", "panel-audit", "panel-puzzles"):
        pos = html.index(f'id="{panel}"')
        assert main_start < pos < main_end, f"{panel} sits outside <main>"


def test_index_and_the_service_worker_agree_on_the_stamped_registry():
    html = _read(INDEX)
    sw = _read(SW_JS)
    refs = set(re.findall(r'(?:href|src)="((?:styles/)?[a-z0-9_-]+\.(?:css|js))\?v=', html))
    refs -= set(STAMPED_DATA)
    assert refs == set(STAMPED_SCRIPTS), (
        f"index.html references but the registry lacks: {sorted(refs - set(STAMPED_SCRIPTS))}; "
        f"registry lists but index.html never loads: {sorted(set(STAMPED_SCRIPTS) - refs)}")
    for name in STAMPED_SCRIPTS:
        assert f"'{name}?v=" in sw, f"sw.js does not precache {name}"
        assert (DOCS / name).exists(), f"{name} is registered but missing on disk"


def test_shell_stylesheets_stay_small():
    for name in SHELL_STYLESHEETS:
        lines = _read(DOCS / "styles" / name).count("\n")
        assert lines <= 300, f"styles/{name} is {lines} lines; split it"


def test_the_removed_stylesheets_stay_removed():
    for name in ("02-header.css", "13-page-tabs.css"):
        assert not os.path.exists(DOCS / "styles" / name), f"styles/{name} is back"
