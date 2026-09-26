"""Token discipline for docs/styles/.

tokens.css is the single home of every colour. Two themes must declare the
same raw palette so no role silently falls back in one of them, every
`var(--x)` anywhere in the stylesheets must resolve to a declaration
(`--text3` and `--font-mono` were used for months without being defined),
and hard-coded colour literals outside the token file are ratcheted down
to zero as the component passes land.
"""
import glob
import os
import re

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
STYLES = os.path.join(DOCS, "styles")
TOKENS = os.path.join(STYLES, "tokens.css")

# Files allowed to carry raw colour values.
LITERAL_EXEMPT = {"tokens.css", "fonts.css"}

# Lower this as literals are retired; never raise it.
LITERAL_CEILING = 0

DECL_RE = re.compile(r"(--[a-zA-Z0-9-]+)\s*:")
VAR_RE = re.compile(r"var\(\s*(--[a-zA-Z0-9-]+)")
LITERAL_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _block(css, selector_start):
    """The body of the first block whose selector text starts with the given text."""
    idx = css.find(selector_start)
    assert idx >= 0, f"selector {selector_start!r} not found in tokens.css"
    start = css.index("{", idx)
    depth, i = 0, start
    while i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[start + 1:i]
        i += 1
    raise AssertionError("unbalanced braces in tokens.css")


def _stylesheets():
    files = sorted(glob.glob(os.path.join(STYLES, "*.css")))
    assert files, "docs/styles/ has no stylesheets"
    return files


def test_light_and_dark_declare_the_same_raw_palette():
    css = _strip_comments(_read(TOKENS))
    light = set(DECL_RE.findall(_block(css, ':root,\n:root[data-theme="light"]')))
    dark = set(DECL_RE.findall(_block(css, ':root[data-theme="dark"]')))
    assert light == dark, (
        f"raw palette differs between themes: only light={sorted(light - dark)}, "
        f"only dark={sorted(dark - light)}")


def test_every_var_reference_resolves():
    declared = set()
    referenced = {}
    for path in _stylesheets():
        css = _strip_comments(_read(path))
        declared.update(DECL_RE.findall(css))
        for name in VAR_RE.findall(css):
            referenced.setdefault(name, os.path.basename(path))
    # var(--x, fallback) still needs --x declared: a fallback hides the miss.
    missing = {n: f for n, f in referenced.items() if n not in declared}
    assert not missing, f"var() references with no declaration: {missing}"


def test_colour_literals_outside_the_token_file_stay_under_the_ceiling():
    count = 0
    for path in _stylesheets():
        if os.path.basename(path) in LITERAL_EXEMPT:
            continue
        css = _strip_comments(_read(path))
        # Print rules keep their own literal palette on purpose.
        css = re.sub(r"@media print\s*\{.*", "", css, flags=re.S)
        count += len(LITERAL_RE.findall(css))
    assert count <= LITERAL_CEILING, (
        f"{count} colour literals outside tokens.css (ceiling {LITERAL_CEILING}); "
        f"route new colours through the semantic tokens")


def test_no_monolithic_stylesheet_remains():
    assert not os.path.exists(os.path.join(DOCS, "styles.css")), (
        "docs/styles.css is back; the stylesheet lives in docs/styles/*.css")
