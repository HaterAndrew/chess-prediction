"""Guards for the classic-script split (C0).

The site deliberately loads its scripts as classic (non-module) tags in one
shared global scope — that IS the compatibility mechanism that lets
actions.js's bare-global dispatches keep resolving as app.js splits apart.
Two hazards come with it:

1. Two files declaring the same top-level name. `let`/`const` collisions
   throw at load (dead page); `var`/`function` collisions silently override
   whichever file loaded first. Neither is survivable review-by-eye across
   17 files, so pin it.

2. The cache-stamp regex in pipeline/stamping.py has no left boundary:
   stamping "app.js?v=" also rewrites "webapp.js?v=" if such a file ever
   appears. No stamped filename may be a proper suffix of another.
"""

import re
from pathlib import Path

from pipeline.stamping import STAMPED_SCRIPTS

DOCS = Path(__file__).resolve().parent.parent / "docs"

# Page-scope classic scripts share one global namespace. sw.js runs in the
# service-worker scope and cannot collide with them.
PAGE_SCOPE_EXEMPT = {"sw.js"}

DECL_RE = re.compile(r"^(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)",
                     re.M)


def test_no_duplicate_top_level_declarations():
    owners = {}
    dupes = []
    for p in sorted(DOCS.glob("*.js")):
        if p.name in PAGE_SCOPE_EXEMPT:
            continue
        for name in DECL_RE.findall(p.read_text()):
            if name in owners and owners[name] != p.name:
                dupes.append(f"{name} ({owners[name]} + {p.name})")
            owners.setdefault(name, p.name)
    assert not dupes, (
        "top-level declarations collide across page-scope scripts: "
        + ", ".join(sorted(dupes)))


def test_no_stamped_name_is_a_suffix_of_another():
    for a in STAMPED_SCRIPTS:
        for b in STAMPED_SCRIPTS:
            if a != b:
                assert not b.endswith(a), (
                    f"{a!r} is a suffix of {b!r}: the stamp regex has no left "
                    f"boundary, so stamping {a} would clobber {b}'s version")
