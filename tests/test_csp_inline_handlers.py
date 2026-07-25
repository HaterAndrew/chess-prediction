"""CSP and the markup's wiring must agree, in both directions.

This exists because tightening `script-src` shipped a completely dead UI to
production. Removing `'unsafe-inline'` (audit S5) blocks every inline
`onclick=`/`onkeydown=` attribute — the browser reports no error on the page,
the handler functions still exist, `elementFromPoint` still returns the button,
and every panel renders perfectly. The only symptom is that nothing responds to
a click. Rendering was verified; interaction was not.

S5 is now closed properly: the handlers moved to delegation in docs/actions.js
and the CSP dropped `'unsafe-inline'`. So the invariant runs both ways.

  - No inline handlers may come back while the CSP forbids them. A single
    `onclick=` added to generated markup would be a dead control, and dead
    controls are invisible to every check short of clicking one.
  - The CSP may not be loosened back without a reason, because that quietly
    re-opens the door for the attribute to work again and the guard to rot.
  - Every `data-act` in the markup must resolve to a real action, since a typo
    now fails the same silent way an inline handler used to.
"""
import os
import re

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
INDEX = os.path.join(DOCS, "index.html")
APP_JS = os.path.join(DOCS, "app.js")
ACTIONS_JS = os.path.join(DOCS, "actions.js")

# Attributes that are inline script under CSP, i.e. blocked without
# 'unsafe-inline' (or 'unsafe-hashes' plus a hash per handler).
HANDLER_ATTR = re.compile(
    r'\son(click|keydown|keyup|input|change|submit|focus|blur|mouse\w+)\s*=', re.I)

MARKUP_FILES = (INDEX, APP_JS)


def _read(path):
    with open(path) as f:
        return f.read()


def _csp_script_src():
    """The script-src directive from index.html's CSP meta tag, or None.

    The content attribute is double-quoted and its VALUE contains single quotes
    ('self', 'unsafe-inline'), so the closing delimiter has to be matched
    explicitly. A class excluding both quote characters stops at the first
    'self' and silently returns no directive — which made the first version of
    this test fail for the wrong reason.
    """
    html = _read(INDEX)
    m = re.search(
        r'http-equiv=["\']Content-Security-Policy["\']\s+content="([^"]+)"', html)
    if not m:
        return None
    for directive in m.group(1).split(';'):
        directive = directive.strip()
        if directive.startswith('script-src'):
            return directive
    return None


def _inline_handlers(path):
    return HANDLER_ATTR.findall(_read(path))


def test_no_inline_handlers_remain_in_the_markup():
    found = {os.path.basename(p): len(_inline_handlers(p)) for p in MARKUP_FILES}
    total = sum(found.values())
    assert total == 0, (
        f"{total} inline event-handler attributes are back ({found}). The CSP "
        f"forbids inline script, so each one is a control that renders normally "
        f"and ignores every click. Wire it through docs/actions.js with "
        f"data-act instead.")


def test_the_csp_forbids_inline_script():
    script_src = _csp_script_src()
    assert script_src is not None, "no script-src directive found in the CSP meta tag"
    assert "'unsafe-inline'" not in script_src, (
        f"script-src permits inline script again: {script_src}. If that is "
        f"deliberate, the reason belongs in the commit; if it is a reflex to "
        f"make a handler work, wire the handler through actions.js instead.")
    assert "'unsafe-hashes'" not in script_src, f"unexpected relaxation: {script_src}"


def test_the_delegation_layer_is_actually_loaded():
    """Nothing on the page responds if this script tag is dropped."""
    html = _read(INDEX)
    assert re.search(r'<script src="actions\.js\?v=[A-Za-z0-9]+"></script>', html), \
        "actions.js is not loaded by index.html; every control would be dead"


def _registered_action_names():
    """Names defined in the three dispatch tables in actions.js."""
    src = _read(ACTIONS_JS)
    names = set()
    for table in ("ACTIONS", "INPUT_ACTIONS", "KEY_ACTIONS"):
        m = re.search(rf'const {table} = \{{(.*?)\n  \}};', src, re.S)
        assert m, f"could not find the {table} table in actions.js"
        names |= set(re.findall(r"^\s*'([a-z0-9-]+)':", m.group(1), re.M))
    return names


def _referenced_action_names():
    """Names the markup asks for, across static HTML and generated strings."""
    refs = set()
    for path in MARKUP_FILES:
        refs |= set(re.findall(
            r'data-(?:act|inputact|keyact)="([a-z0-9-]+)"', _read(path)))
    return refs


def test_every_action_the_markup_asks_for_exists():
    """A typo'd data-act is silently dead, exactly like the old inline bug."""
    missing = sorted(_referenced_action_names() - _registered_action_names())
    assert not missing, (
        f"markup references actions with no handler in actions.js: {missing}")


def test_the_markup_actually_uses_the_delegation_layer():
    """Guards against a rewrite that drops the attributes and the handlers."""
    refs = _referenced_action_names()
    assert len(refs) >= 30, (
        f"only {len(refs)} distinct actions referenced; the markup was expected "
        f"to be fully delegated")


def test_no_element_carries_a_duplicate_attribute():
    """Catches the migration's own footgun: adding a data-* an element already had.

    Several controls already carried data-filter / data-len / data-tab for their
    own styling logic, and the delegation rewrite added the same attribute a
    second time. Browsers keep the first and ignore the rest, so the page worked
    and the markup was invalid — the kind of thing that stays wrong until the
    day two copies disagree.
    """
    import collections

    offenders = []
    for path in MARKUP_FILES:
        text = _read(path)
        for m in re.finditer(r'<[a-zA-Z][^<>]*>', text):
            tag = m.group(0)
            names = re.findall(r'\s([a-zA-Z-]+)=', tag)
            dupes = [n for n, c in collections.Counter(names).items() if c > 1]
            if dupes:
                line = text[:m.start()].count('\n') + 1
                offenders.append(f"{os.path.basename(path)}:{line} {dupes} {tag[:90]}")
    assert not offenders, "duplicate attributes:\n  " + "\n  ".join(offenders)


def test_no_action_is_registered_but_unused():
    """Dead entries in the table mean a control was removed without its wiring.

    Not fatal to a user, but it is how a registry rots into something nobody
    trusts. Better to hear about it at the moment it happens.
    """
    unused = sorted(_registered_action_names() - _referenced_action_names())
    assert not unused, f"actions defined but never referenced by markup: {unused}"
