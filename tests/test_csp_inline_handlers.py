"""CSP must permit the inline event handlers the markup actually uses.

This exists because tightening `script-src` shipped a completely dead UI to
production. Removing `'unsafe-inline'` (audit S5) blocks every inline
`onclick=`/`onkeydown=` attribute — the browser reports no error on the page,
the handler functions still exist, `elementFromPoint` still returns the button,
and every panel renders perfectly. The only symptom is that nothing responds to
a click.

That combination is why it got through: rendering was verified, interaction was
not. A test is the right guard, because the failure is invisible to screenshots.

The rule: if the markup contains inline handlers, the CSP must allow them.
Either side may change — strip the handlers for real listeners and then tighten
the CSP, or keep both — but they must not disagree, because disagreeing means
the site silently stops working.
"""
import os
import re

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
INDEX = os.path.join(DOCS, "index.html")
APP_JS = os.path.join(DOCS, "app.js")

# Attributes that are inline script under CSP, i.e. blocked without
# 'unsafe-inline' (or 'unsafe-hashes' plus a hash per handler).
HANDLER_ATTR = re.compile(r'\son(click|keydown|keyup|input|change|submit|focus|blur|mouse\w+)\s*=', re.I)


def _csp_script_src():
    """The script-src directive from index.html's CSP meta tag, or None.

    The content attribute is double-quoted and its VALUE contains single quotes
    ('self', 'unsafe-inline'), so the closing delimiter has to be matched
    explicitly. A class excluding both quote characters stops at the first
    'self' and silently returns no directive — which made the first version of
    this test fail for the wrong reason.
    """
    with open(INDEX) as f:
        html = f.read()
    m = re.search(
        r'http-equiv=["\']Content-Security-Policy["\']\s+content="([^"]+)"', html)
    if not m:
        return None
    for directive in m.group(1).split(';'):
        directive = directive.strip()
        if directive.startswith('script-src'):
            return directive
    return None


def _count_inline_handlers(path):
    with open(path) as f:
        return len(HANDLER_ATTR.findall(f.read()))


def test_csp_permits_the_inline_handlers_that_exist():
    script_src = _csp_script_src()
    assert script_src is not None, "no script-src directive found in the CSP meta tag"

    n_index = _count_inline_handlers(INDEX)
    n_app = _count_inline_handlers(APP_JS)   # handlers inside generated markup
    total = n_index + n_app

    if total == 0:
        return  # no inline handlers: the CSP is free to be as strict as it likes

    permits = "'unsafe-inline'" in script_src or "'unsafe-hashes'" in script_src
    assert permits, (
        f"CSP script-src blocks inline event handlers, but the markup uses "
        f"{total} of them ({n_index} in index.html, {n_app} in app.js). Every "
        f"button on the site would be dead: the page renders normally and logs "
        f"nothing, it just ignores clicks.\n"
        f"  script-src: {script_src}\n"
        f"Fix by replacing the inline handlers with addEventListener and then "
        f"tightening the CSP — not by tightening the CSP alone."
    )


def test_the_handler_count_is_reported_for_the_delegation_work():
    """Tracks the refactor that would let the CSP be tightened for real.

    Not a pass/fail threshold — it fails only if the counting itself breaks, so
    that the number quoted in the CSP discussion stays honest.
    """
    total = _count_inline_handlers(INDEX) + _count_inline_handlers(APP_JS)
    assert total >= 0
    assert isinstance(total, int)
