"""The site names counts by the day they cover, not the day they were scraped.

2026-10-14. The nightly lands around 2-3 AM Eastern, so the scrape dated
Oct 14 holds registrations through Oct 13, yet the site labelled the counts
"Oct 14". The files keep the scrape date (the curves bin the same way); the
stamp step writes the covered day into the payload for the labels.
"""
import json

from pipeline import config
from pipeline.stamping import _stamp_stale_flag, counts_through

SCRAPE = ("date,tournament_name,entry_count,active_count,withdrawal_count,url\n"
          "2026-10-13,2026 X Open,5,5,0,u\n"
          "2026-10-14,2026 X Open,7,7,0,u\n"
          "2026-10-12,2026 X Open,4,4,0,u\n")


def test_the_covered_day_is_the_day_before_the_newest_scrape():
    assert counts_through(["2026-10-12", "2026-10-14", "2026-10-13"]) == "2026-10-13"


def test_it_crosses_a_month_boundary():
    assert counts_through(["2026-11-01"]) == "2026-10-31"


def test_no_scrape_has_no_covered_day():
    assert counts_through([]) is None
    assert counts_through(["", None]) is None


def _stamp(tmp_path, monkeypatch, scrape, is_stale):
    wd = tmp_path / "website_data.json"
    wd.write_text(json.dumps({"generated": "2026-10-14", "tournaments": []}))
    csv_path = tmp_path / "daily_scrape.csv"
    if scrape is not None:
        csv_path.write_text(scrape)
    monkeypatch.setattr(config, "WEBSITE_JSON", str(wd))
    monkeypatch.setattr(config, "SCRAPE_CSV", str(csv_path))
    _stamp_stale_flag(is_stale=is_stale)
    return json.loads(wd.read_text())


def test_the_stamp_writes_the_covered_day(tmp_path, monkeypatch):
    assert _stamp(tmp_path, monkeypatch, SCRAPE, False)["counts_through"] == "2026-10-13"


def test_a_failed_scrape_keeps_naming_the_last_day_scraped(tmp_path, monkeypatch):
    """Stale path: the file still ends at the last good scrape, so the label
    stays honest instead of claiming the run day's data."""
    out = _stamp(tmp_path, monkeypatch, SCRAPE, True)
    assert out["is_stale"] is True
    assert out["counts_through"] == "2026-10-13"


def test_no_scrape_file_leaves_the_day_unset(tmp_path, monkeypatch, capsys):
    assert _stamp(tmp_path, monkeypatch, None, False)["counts_through"] is None
    assert "counts_through unset" in capsys.readouterr().out
