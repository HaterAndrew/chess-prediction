"""
Regression tests for the entry-list pass of scrapers/entries.py.

Until 2026-10-20 the code table sent the Eastern Chess Congress to CCA_ECC,
which is the Eastern Class Championships' entry list. The withdrawal pass
treats that page as authoritative and overwrote the Congress gross count with
the Class event's 206 for the whole season, while the CCA index showed 328.
These tests pin both halves: the right code for each Eastern event, and a
guard that refuses an entry-list count far from the index count.
"""

import json

import pytest
import requests

from scrapers import entries
from scrapers.entries import _derive_entry_list_code, scrape_withdrawals


@pytest.mark.parametrize("name, code", [
    ("2026 Eastern Chess Congress (in New Jersey)", "ECCO"),
    ("Eastern Chess Congress", "ECCO"),
    ("2026 Eastern Class Championships (in Connecticut)", "ECC"),
    ("2026 Eastern Open", "EO"),
])
def test_eastern_codes(name, code):
    assert _derive_entry_list_code(name) == code


def _page(active, withdrawn):
    filler = "x" * 1200  # scrape_withdrawals ignores pages under 1000 chars
    return f"<html>{filler}<p>{active} Active Players [+{withdrawn} Withdrawn]</p></html>"


class _FakeResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status


class _FakeSession:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, timeout=None, allow_redirects=False):
        for code, text in self.pages.items():
            if f"/CCA_{code}/" in url or code == url:
                return _FakeResp(text)
        return _FakeResp("not found", status=404)


@pytest.fixture
def run(monkeypatch, tmp_path):
    monkeypatch.setattr(entries.time, "sleep", lambda s: None)
    monkeypatch.setattr(entries, "MISMATCH_PATH", str(tmp_path / "scrape_mismatches.json"))

    def _run(pages, tournaments):
        monkeypatch.setattr(entries, "_create_session", lambda: _FakeSession(pages))
        scrape_withdrawals(tournaments)
        return tournaments, json.loads((tmp_path / "scrape_mismatches.json").read_text())

    return _run


def _t(name, count):
    return {"name": name, "year": 2026, "entry_count": count}


def test_matching_page_overrides_gross(run):
    rows, mismatches = run({"ECCO26": _page(328, 3)},
                           [_t("2026 Eastern Chess Congress (in New Jersey)", 328)])
    assert (rows[0]["entry_count"], rows[0]["active_count"], rows[0]["withdrawal_count"]) == (331, 328, 3)
    assert mismatches["mismatches"] == []


def test_wrong_page_keeps_index_count_and_records_mismatch(run):
    # The 2026-10-20 failure: the page read belongs to a different event.
    rows, mismatches = run({"ECCO26": _page(196, 10)},
                           [_t("2026 Eastern Chess Congress (in New Jersey)", 328)])
    assert (rows[0]["entry_count"], rows[0]["active_count"], rows[0]["withdrawal_count"]) == (328, 328, 0)
    [m] = mismatches["mismatches"]
    assert m["tournament"] == "2026 Eastern Chess Congress (in New Jersey)"
    assert (m["index_count"], m["entry_list_count"]) == (328, 206)


def test_missing_page_for_event_with_entries_is_recorded(run):
    rows, mismatches = run({}, [_t("2026 Eastern Open", 9)])
    assert rows[0]["entry_count"] == 9
    [m] = mismatches["mismatches"]
    assert m["tournament"] == "2026 Eastern Open"
    assert m["entry_list_count"] is None


def test_request_error_is_recorded(run, monkeypatch):
    class _Boom:
        def get(self, url, timeout=None, allow_redirects=False):
            raise requests.ConnectionError("down")

    monkeypatch.setattr(entries, "_create_session", lambda: _Boom())
    scrape_withdrawals([_t("2026 Eastern Open", 9)])
    data = json.loads(open(entries.MISMATCH_PATH).read())
    assert data["mismatches"][0]["entry_list_count"] is None


def test_small_drift_is_tolerated(run):
    # Index and entry list refresh at slightly different times.
    rows, mismatches = run({"EO26": _page(10, 0)}, [_t("2026 Eastern Open", 9)])
    assert rows[0]["entry_count"] == 10
    assert mismatches["mismatches"] == []


@pytest.mark.parametrize("index_count", [288, 289, 303])
def test_index_can_show_active_or_gross_entries(run, index_count):
    rows, mismatches = run({"CHCC26": _page(289, 14)},
                           [_t("2026 Chicago Class", index_count)])
    assert (rows[0]["entry_count"], rows[0]["active_count"], rows[0]["withdrawal_count"]) == (303, 289, 14)
    assert mismatches["mismatches"] == []


def test_event_specific_world_open_lists_do_not_share_counts(run):
    lower = "https://www.chessaction.com/tournaments/advance_entry_list.php?tid=lower26"
    junior = "https://www.chessaction.com/tournaments/advance_entry_list.php?tid=junior26"
    rows, mismatches = run({lower: 'x' * 1200 + 'var alpnewfilename = "advlists/CCA/CCA_WO26lower/CCA_WO26lower_alp_n.html";',
                            junior: 'x' * 1200 + 'var alpnewfilename = "advlists/CCA/CCA_WOU1326/CCA_WOU1326_alp_n.html";',
                            "WO26lower": _page(93, 3), "WOU1326": _page(82, 4)}, [
        {**_t("2026 World Open, lower sections", 93), "entry_list_url": lower},
        {**_t("2026 World Open Under 13 Championship", 82), "entry_list_url": junior},
    ])
    assert [(r["entry_count"], r["active_count"], r["withdrawal_count"]) for r in rows] == [
        (96, 93, 3), (86, 82, 4),
    ]
    assert mismatches["mismatches"] == []


@pytest.mark.parametrize("url", [
    "https://example.invalid/tournaments/advance_entry_list.php?tid=lower26",
    "https://www.chessaction.com@outside.invalid/tournaments/advance_entry_list.php?tid=lower26",
    "http://www.chessaction.com/tournaments/advance_entry_list.php?tid=lower26",
    "https://www.chessaction.com/tournaments/advance_entry_list.php?tid=",
    "https://www.chessaction.com/tournaments/advance_entry_list.php?tid=lower26&extra=",
    "https://www.chessaction.com/tournaments/advance_entry_list.php?tid=lower26&tid=junior26",
    "https://www.chessaction.com/admin/registrations.php?tid=lower26",
])
def test_event_list_override_cannot_fetch_an_untrusted_url(url):
    with pytest.raises(ValueError, match="entry-list URL"):
        entries._entry_list_url({**_t("2026 World Open, lower sections", 93), "entry_list_url": url})


def test_index_preserves_each_cards_own_entry_list_url():
    html = """
    <a href="tournaments/index.php?view=entries&tid=lower26">2026 World Open, lower sections</a>
    <div class="text-muted small">Jun 26, 2026 - Jun 28, 2026 State: PA</div>
    <a href="tournaments/advance_entry_list.php?tid=lower26">Entry List [93]</a>
    <a href="tournaments/index.php?view=entries&tid=junior26">2026 World Open Under 13 Championship</a>
    <div class="text-muted small">Jun 29, 2026 - Jun 30, 2026 State: PA</div>
    <a href="tournaments/advance_entry_list.php?tid=junior26">Entry List [82]</a>
    """
    rows = entries._parse_index(html, first_season=2026)
    assert [r["entry_list_url"] for r in rows] == [
        "https://www.chessaction.com/tournaments/advance_entry_list.php?tid=lower26",
        "https://www.chessaction.com/tournaments/advance_entry_list.php?tid=junior26",
    ]


def test_validation_gate_warns_on_todays_mismatches(tmp_path):
    from validation.scrape import validate_scrape_mismatches

    path = tmp_path / "scrape_mismatches.json"
    path.write_text(json.dumps({"date": "2026-10-20", "mismatches": [
        {"tournament": "2026 Eastern Chess Congress (in New Jersey)", "url": "u",
         "index_count": 328, "entry_list_count": 206},
        {"tournament": "2026 Eastern Open", "url": "v",
         "index_count": 9, "entry_list_count": None},
    ]}))
    report = validate_scrape_mismatches(str(path), today="2026-10-20")
    assert report.passed and len(report.warnings) == 2
    assert "328" in report.warnings[0] and "206" in report.warnings[0]
    # Yesterday's file is stale and says nothing about today's scrape.
    assert validate_scrape_mismatches(str(path), today="2026-10-21").warnings == []
    assert validate_scrape_mismatches(str(tmp_path / "absent.json")).warnings == []


def test_index_rejects_entry_list_link_for_another_event():
    html = '''
    <a href="tournaments/index.php?view=entries&tid=lower26">2026 World Open, lower sections</a>
    <div class="text-muted small">Jun 26, 2026 - Jun 28, 2026 State: PA</div>
    <a href="tournaments/advance_entry_list.php?tid=junior26">Entry List [93]</a>
    '''
    with pytest.raises(ValueError, match="does not match"):
        entries._parse_index(html, first_season=2026)


@pytest.mark.parametrize("declarations", [
    'var alpnewfilename = "https://outside.invalid/list.html";',
    'var alpnewfilename = "advlists/CCA/../private.html";',
    'var alpnewfilename = "advlists/CCA/CCA_A26/CCA_A26_alp_n.html";'
    'var alpnewfilename = "advlists/CCA/CCA_B26/CCA_B26_alp_n.html";',
])
def test_unreadable_or_ambiguous_wrapper_records_mismatch(run, declarations):
    url = "https://www.chessaction.com/tournaments/advance_entry_list.php?tid=lower26"
    rows, mismatch = run({url: "x" * 1200 + declarations}, [
        {**_t("2026 World Open, lower sections", 93), "entry_list_url": url}])
    assert rows[0]["entry_count"] == 93
    assert mismatch["mismatches"][0]["entry_list_count"] is None


@pytest.mark.parametrize("junior_unavailable", [False, True])
def test_card_wrapper_static_pipeline_persists_scoped_gross_counts(monkeypatch, tmp_path, junior_unavailable):
    import csv

    specs = [("World Open, top 6 sections", "top26", "WO26", 1066, 1067, 44),
             ("World Open, lower sections", "lower26", "WO26lower", 93, 93, 3),
             ("World Open Under 13 Championship", "junior26", "WU26", 82, 82, 4)]
    html, pages = "", {}
    for name, tid, code, index, active, withdrawn in specs:
        html += (f'<a href="tournaments/index.php?view=entries&tid={tid}">2026 {name}</a>'
                 '<div class="text-muted small">Jun 26, 2026 - Jul 5, 2026 State: PA</div>'
                 f'<a href="tournaments/advance_entry_list.php?tid={tid}">Entry List [{index}]</a>')
        url = f"https://www.chessaction.com/tournaments/advance_entry_list.php?tid={tid}"
        if not (junior_unavailable and tid == "junior26"):
            pages[url] = "x" * 1200 + f'var alpnewfilename = "advlists/CCA/CCA_{code}/CCA_{code}_alp_n.html";'
            pages[code] = _page(active, withdrawn)
    monkeypatch.setattr(entries, "scrape_index", lambda: entries._parse_index(html, first_season=2026))
    monkeypatch.setattr(entries, "_create_session", lambda: _FakeSession(pages))
    monkeypatch.setattr(entries.time, "sleep", lambda _: None)
    monkeypatch.setattr(entries, "CSV_PATH", str(tmp_path / "daily_scrape.csv"))
    monkeypatch.setattr(entries, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(entries, "MISMATCH_PATH", str(tmp_path / "scrape_mismatches.json"))
    monkeypatch.setattr(entries, "sync_metadata", lambda _: None)
    entries.run_scrape_pipeline()
    with (tmp_path / "daily_scrape.csv").open() as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == entries.CSV_FIELDS
        rows = {r["tournament_name"]: r for r in reader}
    assert len(rows) == 3
    assert int(rows["2026 World Open, top 6 sections"]["entry_count"]) == 1111
    assert int(rows["2026 World Open, lower sections"]["entry_count"]) == 96
    junior = rows["2026 World Open Under 13 Championship"]
    assert int(junior["entry_count"]) == (82 if junior_unavailable else 86)
    assert int(junior["withdrawal_count"]) == (0 if junior_unavailable else 4)
    mismatches = json.loads((tmp_path / "scrape_mismatches.json").read_text())["mismatches"]
    assert len(mismatches) == int(junior_unavailable)


def test_entry_list_redirect_is_not_followed(run, monkeypatch):
    calls = []

    class RedirectAdapter(requests.adapters.BaseAdapter):
        def send(self, request, **kwargs):
            calls.append(request.url)
            response = requests.Response()
            response.request = request
            response.url = request.url
            response.status_code = 302 if "chessaction.com" in request.url else 200
            response.headers["Location"] = "https://outside.invalid/private"
            response._content = _page(9, 1).encode()
            return response

        def close(self):
            pass

    session = requests.Session()
    session.mount("https://", RedirectAdapter())
    monkeypatch.setattr(entries, "_create_session", lambda: session)
    tournament = _t("2026 Eastern Open", 9)
    scrape_withdrawals([tournament])
    assert calls == [entries._entry_list_url(tournament)]
    assert tournament["entry_count"] == 9
    mismatch = json.loads(open(entries.MISMATCH_PATH).read())["mismatches"]
    assert mismatch[0]["entry_list_count"] is None
