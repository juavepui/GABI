import pytest

from gabi import config, edgar, storage
from gabi.historical_sec_audit import filing_status, load_concept_dates


def test_filing_status_never_uses_future_or_stale_filing():
    dates = ["2011-02-01", "2013-02-01"]
    assert filing_status(dates, "2011-01-01") == (False, False)
    assert filing_status(dates, "2011-06-01") == (True, True)
    assert filing_status(dates, "2012-12-31") == (True, False)
    assert filing_status(dates, "2013-03-01") == (True, True)


def test_concept_audit_requires_correct_unit_period_and_filing_date(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr("requests.sessions.Session.request",
                        lambda *args, **kwargs: pytest.fail("No network allowed"))
    base = {"tag": "Revenues", "unit": "USD", "start_date": "2011-01-01",
            "end_date": "2011-12-31", "val": 100, "form": "10-K", "fp": "FY", "fy": 2011,
            "filed_date": "2012-02-01", "accn": "a"}
    edgar.upsert_edgar_facts("OLD", [base,
                                      {**base, "unit": "shares", "accn": "b"},
                                      {**base, "end_date": "2013-12-31", "accn": "c"}], cik="1")
    with storage.get_connection() as conn:
        dates = load_concept_dates(conn)
    assert dates[("0000000001", "revenue")] == ["2012-02-01"]
    assert filing_status(dates[("0000000001", "revenue")], "2011-12-31") == (False, False)
