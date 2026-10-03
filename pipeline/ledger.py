"""The forecast ledger: every forecast the site publishes, one row per live
card per run, appended to output/forecast_ledger.csv and never pruned.

update_log.csv keeps 90 days and says nothing about which code produced a
row. The ledger is the record the live scoreboard grades: what the site said
about an event on a given date, from which model, so a forecast can be judged
against the final it was made before.
"""
import csv
import json
import os
from datetime import date

from pipeline import config
from shared.model_version import MODEL_LABEL, code_commit, model_hash

LEDGER_FIELDS = [
    'as_of_date', 'run_ts', 'origin', 'published',
    'family', 'year', 'event_start', 'T', 'days_remaining', 'status',
    'count', 'gross_count', 'withdrawal_count',
    'point', 'ci_lower', 'ci_upper', 'ci_level',
    'route', 'tier', 'low_confidence', 'is_stale',
    'model_label', 'model_hash', 'code_commit',
]


def days_before(event_start, as_of):
    """Whole days from the forecast date to the event's start, or '' when a
    date is missing or malformed."""
    try:
        return (date.fromisoformat(event_start) - date.fromisoformat(as_of)).days
    except (TypeError, ValueError):
        return ''


def _blank(value):
    return '' if value is None else value


# Origins whose rows are the forecasts the site showed: the CI run, and the
# backfill rebuilt from its published commits. A local run's output never
# reaches the site.
PUBLISHED_ORIGINS = ('nightly', 'backfill')


def run_origin(env=os.environ):
    """'nightly' on the GitHub Actions runner, whose commit is what the site
    serves; 'local' anywhere else."""
    return 'nightly' if env.get('GITHUB_ACTIONS') == 'true' else 'local'


def ledger_rows(website, *, run_ts, model_label, model_hash, code_commit, origin='nightly'):
    """One row per live card in a website_data.json payload, then an
    unpublished row (published 0) for each stand-in route the card carries in
    shadow_forecasts. The card's own row counts as published only for a
    PUBLISHED_ORIGINS run: the scoreboard keeps each day's last published
    run, so a local run marked published would displace the forecast the site
    showed. The forecast date is the
    payload's `generated` date (the pipeline's local day), falling back to
    the run timestamp's date."""
    as_of = website.get('generated') or str(run_ts)[:10]
    stale = int(bool(website.get('is_stale')))
    published = int(origin in PUBLISHED_ORIGINS)
    rows = []
    for card in website.get('tournaments', []):
        if card.get('status') != 'live':
            continue
        row = {
            'as_of_date': as_of, 'run_ts': run_ts, 'origin': origin, 'published': published,
            'family': card.get('family', ''), 'year': _blank(card.get('year')),
            'event_start': _blank(card.get('event_start')),
            'T': days_before(card.get('event_start'), as_of),
            'days_remaining': _blank(card.get('days_remaining')),
            'status': card.get('status', ''),
            'count': _blank(card.get('current_count')),
            'gross_count': _blank(card.get('gross_count')),
            'withdrawal_count': _blank(card.get('withdrawal_count')),
            'point': _blank(card.get('point_estimate')),
            'ci_lower': _blank(card.get('ci_lower')),
            'ci_upper': _blank(card.get('ci_upper')),
            'ci_level': _blank(card.get('ci_level')),
            'route': card.get('prediction_source') or '',
            'tier': card.get('prediction_tier') or '',
            'low_confidence': int(bool(card.get('low_confidence'))),
            'is_stale': stale,
            'model_label': model_label, 'model_hash': model_hash, 'code_commit': code_commit,
        }
        rows.append(row)
        rows.extend(shadow_rows(row, card.get('shadow_forecasts') or []))
    return rows


def shadow_rows(published, shadows):
    """The published row restated as each stand-in route's unpublished forecast."""
    return [{**published, 'published': 0, 'route': s['route'], 'tier': '',
             'point': s['point'], 'ci_lower': s['ci_lower'], 'ci_upper': s['ci_upper']}
            for s in shadows]


def append_ledger(rows, path):
    """Append rows under the ledger header, writing it for a new file. A file
    whose header is anything else is refused: appending under another header
    would misalign every row after it, silently."""
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    if exists:
        with open(path, newline='') as fh:
            header = next(csv.reader(fh), None)
        if header != LEDGER_FIELDS:
            raise ValueError(f"{path} header {header} is not the ledger header {LEDGER_FIELDS}")
    with open(path, 'a', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=LEDGER_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def step_record_forecasts():
    """Append tonight's published forecasts to the ledger."""
    with open(config.WEBSITE_JSON) as fh:
        website = json.load(fh)
    origin = run_origin()
    rows = ledger_rows(website, run_ts=config.RUN_TS, model_label=MODEL_LABEL,
                       model_hash=model_hash(), code_commit=code_commit(), origin=origin)
    n = append_ledger(rows, config.FORECAST_LEDGER)
    published = sum(1 for r in rows if r['published'])
    print(f"  Recorded {published} published and {n - published} unpublished "
          f"({origin}) forecasts in {config.FORECAST_LEDGER}")
    return n
