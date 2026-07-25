"""
Guard: published test fixtures must not carry real-person data (audit v3 S2).

The hotel-audit fixtures previously held full names, home city/state/ZIP and
payer links in a public repo — including minor-player -> home-address ->
paying-parent clusters, i.e. exactly the join hotel_audit.py produces. They were
replaced with obviously-synthetic people that preserve every structural property
the tests exercise (casing variants, middle names, title annotations, sibling
address sharing, non-player payers, malformed city cells, stripped leading
zeros).

This test keeps them that way. It does not attempt to detect "real names" in
general — that is not decidable. It pins the specific identities that were
removed, so a revert or a fresh export dropped in from production fails loudly
rather than silently republishing personal data.
"""
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# Surnames, given names and places that were in the fixtures before the v3 S2
# scrub. Any reappearance means real export data came back.
REMOVED_IDENTIFIERS = [
    "Brightwater", "Quillon", "Orlando", "Pemberly", "Sunderholm", "Jonquil",
    "Marbleton", "Marigold", "Dennison", "Kingsley", "Rosalind", "Torrance", "Delphine",
    "Zephyr", "Merrick",
]

# Files that are published and must stay synthetic.
SCANNED = [
    "tests/fixtures/admin_export_sample.csv",
    "tests/fixtures/cca_entry_list_wo26.html",
    "tests/test_hotel_audit.py",
    "tests/test_audit_js_parity.py",
    "hotel_audit.py",
    "docs/audit.js",
]


@pytest.mark.parametrize("rel", SCANNED)
def test_no_removed_identifiers_reappear(rel):
    path = REPO / rel
    if not path.exists():
        pytest.skip(f"{rel} not present")
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    found = [n for n in REMOVED_IDENTIFIERS if n.lower() in lowered]
    assert not found, (
        f"{rel} contains identifiers removed by the v3 S2 scrub: {found}. "
        "If a real admin export was copied in, replace it with synthetic data.")


def test_export_fixture_has_no_extra_pii_columns():
    """A real export carries more columns than the audit join needs. Keep the
    fixture to the minimum so a fuller dump cannot be pasted in unnoticed."""
    path = REPO / "tests/fixtures/admin_export_sample.csv"
    header = path.read_text(encoding="utf-8").splitlines()[0]
    cols = {c.strip().strip('"') for c in header.split(",")}
    allowed = {"LastName", "FirstName", "City", "State", "ZipCode", "PayerName"}
    extra = cols - allowed
    assert not extra, f"unexpected columns in the export fixture: {sorted(extra)}"

    banned = {"Email", "Phone", "Address", "DOB", "BirthDate", "USCF",
              "MemberID", "Street", "CreditCard"}
    assert not (cols & banned), f"PII-bearing columns present: {sorted(cols & banned)}"


def test_export_fixture_stays_small():
    """A handful of rows is enough to exercise every shape. A large file is a
    sign someone dropped in a production export."""
    path = REPO / "tests/fixtures/admin_export_sample.csv"
    rows = [r for r in path.read_text(encoding="utf-8").splitlines() if r.strip()]
    assert len(rows) <= 25, f"export fixture grew to {len(rows)} rows — is this real data?"


def test_structural_shapes_survive_the_scrub():
    """The scrub must not have flattened what the fixture is for."""
    import csv
    path = REPO / "tests/fixtures/admin_export_sample.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    # Two players sharing one address and one paying parent.
    by_payer = {}
    for r in rows:
        by_payer.setdefault(r["PayerName"].lower(), []).append(r)
    assert any(len(v) >= 2 for v in by_payer.values()), "no shared-payer cluster left"

    # A ZIP whose leading zero was eaten by a spreadsheet.
    assert any(len(r["ZipCode"]) == 4 for r in rows), "no stripped-leading-zero ZIP left"

    # A city cell polluted with "City, ST ZIP".
    assert any("," in r["City"] for r in rows), "no malformed city cell left"

    # Casing variation between a row and its payer spelling.
    assert any(r["PayerName"].isupper() for r in rows), "no all-caps payer left"
