"""The financial join must identify the actual registration set, not equal totals."""
import hashlib
import json
from pathlib import Path

from scrapers.entries import ObservedCounts
from tournament_aliases import FAMILY_GROUPS, CCA_CANONICALIZE, canonicalize_family
from pipeline.receipt_metadata import attach_receipt_observations


def test_complete_public_identifiers_get_an_observation_and_cohort_hash():
    page = '<span id="#bname_2"></span><span id="#bname_1"></span><span id="#bname_2"></span>'
    counts = ObservedCounts(1, 1, page)
    hashes = sorted(hashlib.sha256(i.encode()).hexdigest() for i in ['1', '2'])
    assert counts == (1, 1)
    assert counts.cohort_hash == hashlib.sha256('\n'.join(hashes).encode()).hexdigest()
    assert counts.observed_at.endswith('+00:00')


def test_incomplete_or_missing_identity_markup_never_claims_a_verified_set():
    assert ObservedCounts(2, 0, '<span id="#bname_1"></span>').cohort_hash is None
    assert ObservedCounts(2, 0, '').observed_at is None


def test_finance_family_names_follow_the_existing_repository_aliases():
    expected = {v: group[0] for group in FAMILY_GROUPS for v in group}
    expected.update({k: canonicalize_family(v) for k, v in CCA_CANONICALIZE.items()})
    path = Path(__file__).resolve().parents[1] / 'worker/src/finance/aliases.json'
    assert json.loads(path.read_text()) == expected


def test_latest_missing_cohort_clears_previous_metadata_instead_of_inheriting_it(tmp_path):
    path = tmp_path / 'scrape.csv'
    path.write_text('date,tournament_name,entry_count,count_observed_at,count_cohort_hash\n'
                    '2026-11-08,2026 Example Open,5,2026-11-08T01:00:00+00:00,' + 'a' * 64 + '\n'
                    '2026-11-09,2026 Example Open,5,,\n')
    data = {'tournaments':[{'family':'Example Open','year':2026,'current_count':5,'point_estimate':10}]}
    attach_receipt_observations(data, path)
    assert data['tournaments'][0]['count_cohort_hash'] is None
    assert data['tournaments'][0]['point_estimate'] == 10
