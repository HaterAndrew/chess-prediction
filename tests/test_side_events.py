"""The side-event pattern is one definition, used everywhere.

Four drifted copies existed until 2026-07-31 (model wide, three narrow).
These tests pin the single home and the behavior the unification fixed.
"""
import os

from shared.side_events import SIDE_EVENT_PATTERN, SIDE_EVENT_RE

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_healthcheck_uses_the_shared_object():
    from healthcheck import checks
    assert checks._BLITZ_RE is SIDE_EVENT_RE


def test_no_inline_copies_remain():
    """No consumer may re-literal the alternation; the drifted-copy failure
    mode this guards against is exactly how Action events kept being graded
    for months."""
    fragment = "Bughouse|Armageddon"
    offenders = []
    for rel in ("model/fitting.py", "sitebuild/main.py", "perf/folds.py",
                "healthcheck/checks.py"):
        with open(os.path.join(PROJECT_DIR, rel), encoding="utf-8") as fh:
            if fragment in fh.read():
                offenders.append(rel)
    assert not offenders, f"inline side-event regex copies in: {offenders}"


def test_pattern_matches_the_full_side_event_class():
    matches = [
        "World Open Blitz Championship",
        "ICC August Rapid",
        "September Action",
        "World Open G/7 Championship",
        "World Open G 45",
        "World Open G7 Championship",   # fused spelling escaped every old copy
        "ICC March G 60",
    ]
    for name in matches:
        assert SIDE_EVENT_RE.search(name), name


def test_pattern_leaves_main_events_alone():
    non_matches = [
        "Golden State Open",            # G followed by letters, not digits
        "George Washington Open",
        "Continental Open",
        "New York State Scholastic Championships Grades K-8",
        "National Chess Congress",
        "Eastern Class Championships",
    ]
    for name in non_matches:
        assert not SIDE_EVENT_RE.search(name), name


def test_pattern_string_and_compiled_agree():
    import re
    assert re.compile(SIDE_EVENT_PATTERN, re.IGNORECASE).pattern == SIDE_EVENT_RE.pattern
