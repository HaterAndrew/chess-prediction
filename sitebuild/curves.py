"""Template-curve builder.

Resolved 2026-07-31 (was a parked ledger question): the 04d copy was
line-identical to model/curves.py apart from int()/float() casts on the
output dict — same filters, same interpolation, same T_GRID (both
np.arange(0, 121)). One implementation lives in model/curves.py; golden
byte-compare confirms identical site output through this re-export.
"""
from model.curves import build_template_curves  # noqa: F401
