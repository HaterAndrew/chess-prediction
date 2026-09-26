"""The shell: the four-item nav, the two group sheets behind Model and Tools,
the tournament picker's markup, the asset registries, and the markup hygiene
the redesign set.

The 2026-09 Wallchart shell replaced the registry rail (a side rail on a
desktop, a bottom bar with More on a phone) with a chess-app structure: one
top bar where the tournament is the subject, a four-item nav (Forecast,
Season, Model, Tools) that becomes the bottom bar on a phone, and one picker
for every width. Each rule here is one that a later edit could break one
attribute at a time without any other test noticing: a view with no button
is unreachable, a stylesheet missing from the stamp list ships uncached, a
glyph entity in the chrome is a font-dependent icon, a font file missing
from the precache renders the sheet in the fallback face offline.
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
PICKERS_JS = DOCS / "pickers.js"
SW_JS = DOCS / "sw.js"
FONTS_CSS = DOCS / "styles" / "fonts.css"
SHELL_STYLESHEETS = ("shell.css", "controls.css", "overlays.css", "picker.css", "forecast.css", "sections.css", "season.css")

NAV_ITEMS = ["Forecast", "Season", "Model", "Tools"]
GROUPS = {"model": ["performance", "audit", "about"], "tools": ["compare", "ask", "email", "puzzles"]}

# AP style keeps these lowercase inside a title.
SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor",
               "of", "on", "or", "the", "to", "up", "yet"}


def _read(path):
    return path.read_text(encoding="utf-8")


def _element(html, open_tag, close_tag):
    start = html.index(open_tag)
    return html[start:html.index(close_tag, start)]


def _topbar(html):
    return _element(html, '<header class="topbar"', "</header>")


def _nav(html):
    return _element(html, '<nav id="primaryNav"', "</nav>")


def _sheet(html, group):
    return _element(html, f'<div id="{group}Sheet"', "</div>\n</div>")


def _js_list(src, name):
    m = re.search(rf"const {name} = \[(.*?)\];", src, re.S)
    assert m, f"{name} not found"
    return re.findall(r"'([a-z]+)'", m.group(1))


def _view_buttons(chunk):
    """{tab: label} for every page-tab button in a chunk of markup."""
    return {m.group(1): m.group(2) for m in re.finditer(
        r'<button[^>]*data-act="page-tab"[^>]*data-tab="([a-z]+)"[^>]*>.*?<b>([^<]+)</b>', chunk, re.S)}


def _title_case(label):
    words = label.split()
    return all(w[0].isupper() or (i > 0 and w in SMALL_WORDS) for i, w in enumerate(words))


def test_the_nav_holds_four_items_in_order():
    nav = _nav(_read(INDEX))
    labels = re.findall(r"<b>([^<]+)</b>", nav)
    assert labels == NAV_ITEMS, labels
    views = _view_buttons(nav)
    assert list(views) == ["predictions", "season"], "Forecast and Season are the nav's two views"
    for group in GROUPS:
        assert re.search(rf'<button[^>]*data-act="open-group-sheet"[^>]*data-group="{group}"[^>]*aria-controls="{group}Sheet"', nav), \
            f"the {group} item does not open its sheet"


def test_every_view_has_a_button_a_panel_and_a_home():
    html = _read(INDEX)
    views = _js_list(_read(APP_JS), "VALID_TABS")
    buttons = dict(_view_buttons(_nav(html)))
    for group, members in GROUPS.items():
        sheet_views = _view_buttons(_sheet(html, group))
        assert list(sheet_views) == members, f"the {group} sheet lists {list(sheet_views)}"
        buttons.update(sheet_views)
    for tab in views:
        assert tab in buttons, f"no button for the {tab} view"
        assert f'id="ptab-{tab}"' in html, f"the {tab} button lost its id"
        assert f'id="panel-{tab}"' in html, f"no panel for the {tab} view"
    assert set(buttons) == set(views), "the shell lists a view the router does not know"
    groups = dict(re.findall(r"^\s*(model|tools): \[([^\]]+)\]", _read(SHELL_JS), re.M))
    for group, members in GROUPS.items():
        assert re.findall(r"'([a-z]+)'", groups[group]) == members, f"shell.js NAV_GROUPS.{group} disagrees with the markup"


def test_swipe_order_lists_every_view_once():
    app = _read(APP_JS)
    order = _js_list(app, "PAGE_TAB_ORDER")
    assert sorted(order) == sorted(set(order)), "a view appears twice in PAGE_TAB_ORDER"
    assert set(order) == set(_js_list(app, "VALID_TABS"))


def test_the_subject_opens_the_one_picker():
    html = _read(INDEX)
    topbar = _topbar(html)
    assert re.search(r'<button[^>]*id="headerTournLabel"[^>]*data-act="open-tourney-picker"[^>]*aria-controls="tourneySheet"', topbar)
    for part in ('id="tournLabel"', 'id="tournStatus"', 'id="tournTminus"'):
        assert part in topbar, f"the subject lost {part}"
    picker = _element(html, '<div id="tourneySheet"', "</div>\n</div>")
    for part in ('id="pickerSegments"', 'id="pickerSearchInput"', 'data-inputact="filter-tourney-hist"',
                 'id="pickerList"', 'role="listbox"'):
        assert part in picker, f"the picker lost {part}"
    pickers = _read(PICKERS_JS)
    for fn in ("function openTourneyPicker(", "function renderTourneyPicker(", "function setTourneyTab(",
               "function filterTourneyHistResults(", "function selectFromTourneyPicker("):
        assert fn in pickers, f"pickers.js lost {fn}"
    for key in ("'ArrowDown'", "'ArrowUp'", "'Home'", "'End'", "'Enter'"):
        assert key in pickers, f"the picker's keyboard navigation lost {key}"


def test_the_rail_the_more_sheet_and_the_dropdowns_are_gone():
    relics = ('id="rail"', "railToggle", "toggle-rail", "moreSheet", "open-more-sheet", "dropMenu_",
              'id="tabBar"', "renderTabs", "toggle-drop", "select-from-drop", "filter-hist\"", "openDrop",
              "drawer-open", "tournDot")
    for path in (INDEX, APP_JS, ACTIONS_JS, SHELL_JS, PICKERS_JS):
        text = _read(path)
        for relic in relics:
            assert relic not in text, f"{relic} is back in {path.name}"


def test_view_titles_match_the_button_labels_in_title_case():
    html = _read(INDEX)
    titles = dict(re.findall(r"^\s*([a-z]+): '([^']+)',", _read(SHELL_JS), re.M))
    buttons = dict(_view_buttons(_nav(html)))
    for group in GROUPS:
        buttons.update(_view_buttons(_sheet(html, group)))
    for tab, label in buttons.items():
        assert titles.get(tab) == label, f"{tab}: button says {label!r}, VIEW_TITLES says {titles.get(tab)!r}"
        assert _title_case(label), f"{label!r} is not in AP title case"
    for label in NAV_ITEMS:
        assert _title_case(label)


def test_the_shell_markup_carries_no_glyph_entities():
    html = _read(INDEX)
    chunks = [("top bar", _topbar(html)), ("picker", _element(html, '<div id="tourneySheet"', "</div>\n</div>"))]
    chunks += [(f"{g} sheet", _sheet(html, g)) for g in GROUPS]
    for name, chunk in chunks:
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
    assert html.count('id="primaryNav"') == 1, "the nav appears more than once"


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


def test_every_font_file_is_on_disk_and_precached():
    """fonts.css names the files; the service worker precaches them so an
    offline visit still sets the sheet in Archivo and Courier Prime."""
    files = re.findall(r"url\('\.\./(fonts/[^']+)'\)", _read(FONTS_CSS))
    assert files, "fonts.css declares no font files"
    sw = _read(SW_JS)
    for name in files:
        assert (DOCS / name).exists(), f"{name} is declared but missing on disk"
        assert f"'{name}'" in sw, f"sw.js does not precache {name}"
    precached = set(re.findall(r"'(fonts/[^']+)'", sw))
    assert precached == set(files), f"sw.js precaches font files fonts.css never uses: {sorted(precached - set(files))}"
    assert re.search(r"font-family: 'Archivo'", _read(FONTS_CSS)) and "Courier Prime" in _read(FONTS_CSS)
    assert "Inter" not in _read(FONTS_CSS) and "Plex" not in _read(FONTS_CSS), "the registry faces are back"


def test_shell_stylesheets_stay_small():
    for name in SHELL_STYLESHEETS:
        lines = _read(DOCS / "styles" / name).count("\n")
        assert lines <= 300, f"styles/{name} is {lines} lines; split it"


def test_the_removed_stylesheets_stay_removed():
    for name in ("02-header.css", "04-tab-bar.css", "05-delta-banner.css", "06-mobile-predictions.css", "07-hero.css",
                 "08-chart.css", "09-timeline.css", "11-tables.css", "12-calendar.css", "13-page-tabs.css", "cards.css"):
        assert not os.path.exists(DOCS / "styles" / name), f"styles/{name} is back"
