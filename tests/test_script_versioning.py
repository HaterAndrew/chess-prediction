"""Script cache-busters must follow their file's content (v3 P5, extended).

P5 fixed the data file's `?v=` and left the scripts on hand-maintained numbers.
That fails the same way in the other direction: a script's version only moves if
someone remembers to bump it, so a shipped fix can sit behind a cached copy of
the old file indefinitely. Two app.js fixes went out behind `?v=40` before this
was caught.
"""

import pytest


import auto_update  # noqa: E402
import pipeline.config  # noqa: E402


@pytest.fixture
def site(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "app.js").write_text("console.log(1);\n")
    (docs / "boot.js").write_text("console.log(2);\n")
    index = docs / "index.html"
    index.write_text(
        '<script src="boot.js?v=1"></script>\n'
        '<script src="app.js?v=40"></script>\n'
    )
    # Patch the defining module (P5): the stampers derive targets from
    # pipeline.config.SITE_DIR at call time; the shim's copy is inert.
    monkeypatch.setattr(pipeline.config, "SITE_DIR", str(docs))
    monkeypatch.setattr(pipeline.config, "INDEX_HTML", str(index))
    return {"docs": docs, "index": index}


def _version_of(index_text, name):
    import re
    m = re.search(rf'{re.escape(name)}\?v=([A-Za-z0-9]+)', index_text)
    return m.group(1) if m else None


def test_hand_number_is_replaced_by_a_content_hash(site):
    auto_update._stamp_script_versions()
    v = _version_of(site["index"].read_text(), "app.js")
    assert v is not None and v != "40"
    assert len(v) == 10


def test_version_changes_when_the_script_changes(site):
    auto_update._stamp_script_versions()
    first = _version_of(site["index"].read_text(), "app.js")

    (site["docs"] / "app.js").write_text("console.log(1); // fix\n")
    auto_update._stamp_script_versions()
    second = _version_of(site["index"].read_text(), "app.js")

    assert first != second, "a changed script must get a new URL"


def test_version_is_stable_when_the_script_is_not_touched(site):
    """Otherwise every nightly run invalidates every client's cache for nothing."""
    auto_update._stamp_script_versions()
    first = _version_of(site["index"].read_text(), "app.js")
    auto_update._stamp_script_versions()
    assert _version_of(site["index"].read_text(), "app.js") == first


def test_each_script_is_stamped_independently(site):
    auto_update._stamp_script_versions()
    text = site["index"].read_text()
    assert _version_of(text, "app.js") != _version_of(text, "boot.js")

    boot_before = _version_of(text, "boot.js")
    (site["docs"] / "app.js").write_text("console.log(99);\n")
    auto_update._stamp_script_versions()
    text = site["index"].read_text()
    assert _version_of(text, "boot.js") == boot_before, \
        "editing app.js must not churn boot.js's cache entry"


def test_missing_script_is_skipped_not_crashed(site):
    (site["docs"] / "boot.js").unlink()
    auto_update._stamp_script_versions()  # must not raise
    assert _version_of(site["index"].read_text(), "boot.js") == "1"
