"""Append only a verified deployment's producer-stamped forecasts, once."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.ledger import append_ledger, ledger_rows
from verify_checksums import generate_manifest


def record_confirmed(expected, root=Path('output'), verified_at=None):
    digest = hashlib.sha256(expected).hexdigest()
    candidate_path = root / 'forecast_candidate.json'
    # Enrichment or recovery may deploy an existing data snapshot without a
    # new forecast candidate. Never manufacture one under today's model code.
    if not candidate_path.exists():
        return 0
    candidate = json.loads(candidate_path.read_bytes())
    if candidate.get('asset_sha256') != digest:
        if json.loads(expected).get('is_stale'):
            return 0
        raise ValueError('publication_candidate_digest_mismatch')
    fields = {'schema', 'asset_sha256', 'run_ts', 'model_label', 'model_hash', 'code_commit', 'rows'}
    if set(candidate) != fields or candidate['schema'] != 1:
        raise ValueError('invalid_publication_candidate')
    rows = ledger_rows(json.loads(expected), run_ts=candidate['run_ts'],
                       model_label=candidate['model_label'], model_hash=candidate['model_hash'],
                       code_commit=candidate['code_commit'], origin='nightly')
    if rows != candidate['rows']:
        raise ValueError('publication_candidate_does_not_match_asset')
    receipt_path = root / 'forecast_publications.json'
    receipts = json.loads(receipt_path.read_bytes()) if receipt_path.exists() else {}
    if digest in receipts:
        return 0
    verified = verified_at or datetime.now(timezone.utc)
    # Eligibility follows the day visitors actually received the forecast,
    # while the receipt preserves the producer's original timestamp and hash.
    confirmed_rows = ledger_rows({**json.loads(expected), 'generated': verified.date().isoformat()},
                                 run_ts=verified.strftime('%Y-%m-%d %H:%M:%S'),
                                 model_label=candidate['model_label'], model_hash=candidate['model_hash'],
                                 code_commit=candidate['code_commit'], origin='nightly')
    paths = [root / 'forecast_ledger.csv', receipt_path, root / 'checksums.json']
    originals = {path: path.read_bytes() if path.exists() else None for path in paths}
    try:
        count = append_ledger(confirmed_rows, paths[0])
        receipts[digest] = {'producer_run_ts': candidate['run_ts'],
                            'producer_as_of_date': json.loads(expected).get('generated'),
                            'verified_at': verified.isoformat(),
                            'model_hash': candidate['model_hash'], 'rows': count}
        receipt_path.write_text(json.dumps(receipts, indent=2, sort_keys=True) + '\n')
        generate_manifest(str(root))
    except (OSError, ValueError, TypeError):
        try:
            for path, original in originals.items():
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
        except OSError:
            raise ValueError('publication_rollback_failed') from None
        raise
    return count
