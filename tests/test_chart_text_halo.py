"""Chart text is never drawn bare where a line can cross it.

A label inside a plot sits on a sheet-coloured halo (chartHaloText in
docs/chart_kit.js), so the lines and marks it meets pass behind it. Every
other fillText in the page's scripts must say, on its own line or the line
above, where its background comes from: a "halo:" comment naming the box
under it or the padding outside the plot. A bare call fails this test.

The runtime companion, scripts/check_chart_text.py, measures the drawn
labels for overlaps, crossings and clipping; run it after any chart change.
"""
import pathlib
import re

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
BUNDLE = {"site.js", "sw.js"}


def _bare_fill_text_calls():
    bare = []
    for path in sorted(DOCS.glob("*.js")):
        if path.name in BUNDLE:
            continue
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            if not re.search(r"\.fillText\(", line):
                continue
            context = line + (lines[i - 1] if i else "")
            if "halo:" not in context:
                bare.append(f"{path.name}:{i + 1}: {line.strip()}")
    return bare


def test_every_canvas_label_names_its_halo():
    bare = _bare_fill_text_calls()
    assert not bare, (
        "canvas text drawn without a halo (use chartHaloText, or add a "
        "'halo:' comment saying why nothing can cross it):\n" + "\n".join(bare))
