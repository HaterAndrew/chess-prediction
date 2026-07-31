"""Quick-chess side-event detection, shared across the pipeline.

One event class, one definition. Until 2026-07-31 this pattern existed as
four drifted copies: the model's wide version (with Action and G-format
events) and three narrow copies in sitebuild, perf, and healthcheck that
predated the widening and silently kept grading Action events. Families
like "X Blitz", "Y Action", or "World Open G/7 Championship" are
quick-chess side events with massive day-of registration surges: the
model flags them for surge-aware nowcasting (BLITZ_FAMILIES), sitebuild
and perf exclude them from cards and grading (not useful for logistical
planning), and the health scan skips them.

The G alternation accepts slash, space, and fused spellings (G/7, G 45,
G7) — the fused form escaped every earlier copy.
"""
import re

SIDE_EVENT_PATTERN = r"Blitz|Rapid|Bullet|Bughouse|Armageddon|Action|\bG\s*/?\s*\d+"
SIDE_EVENT_RE = re.compile(SIDE_EVENT_PATTERN, re.IGNORECASE)
