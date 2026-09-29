import pandas as pd
import pytest

from gabi import config, edgar, historical_archive, identity, storage
from gabi.historical_backfill import overlaps_membership


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    historical_archive.register_source("test", {"start": "1996-01-02", "end_exclusive": "2016-01-01"})


def test_dated_membership_is_a_separate_source_with_limited_horizon(db):
    frame = pd.DataFrame([("1996-01-02", "AAA,BBB"), ("2000-01-03", "BBB,CCC")], columns=["date", "tickers"])
    assert historical_archive.import_membership("test", frame, "1996-01-02", "2016-01-01") == 2
    result = historical_archive.get_membership("test", "1999-12-31")
    assert result["symbols"] == ["AAA", "BBB"]
    assert result["quality"] == "community_unverified"
    with pytest.raises(ValueError):
        historical_archive.get_membership("test", "2016-01-01")


def test_archive_preserves_raw_close_and_does_not_mix_into_yahoo(db):
    data = pd.DataFrame({"symbol": ["AAA"] * 4, "date": ["2000-01-03", "2000-01-04", "2000-01-05", "2016-01-04"],
                         "open": [100., 0., 100., 100.], "high": [110., 110., 90., 110.],
                         "low": [90.] * 4, "close": [100.] * 4, "adjusted_close": [5.] * 4, "volume": [1000.] * 4})
    for _ in range(2):
        result = historical_archive.import_price_chunk("test", data, {"AAA"}, "1996-01-02", "2016-01-01")
        assert result == {"accepted": 1, "rejected": 2}
    archive = historical_archive.get_prices("test", "AAA", "1996-01-02", "2016-01-01")
    assert len(archive) == 1
    assert archive.iloc[0]["close"] == 100.
    assert archive.iloc[0]["adj_close"] == 5.
    assert archive.attrs["close_basis"] == "as_traded"
    storage.init_db()
    assert storage.get_prices("AAA").empty


def test_current_map_cannot_reassign_old_ticker():
    frame = pd.DataFrame([
        ("OLD", "0000000001", "2000-01-01", "2007-03-05"),
        ("SAFE", "0000000002", "2000-01-01", "2007-03-05"),
        ("LATER", "0000000003", "2017-01-01", "2017-01-01"),
    ], columns=["symbol", "cik", "date_added", "created_at"])
    safe, blocked = historical_archive.unique_historical_ciks(
        frame, {"OLD", "SAFE", "LATER"}, {"OLD": "0000000099", "SAFE": "0000000002"}, {})
    assert safe == {"SAFE": "0000000002"}
    assert blocked["OLD"] == "issuer_conflict_or_reused_ticker"
    assert blocked["LATER"] == "missing_historical_cik"


def test_history_after_removal_does_not_count_as_recovered_prices():
    history = pd.DataFrame([("1996-01-02", "AAA,BBB"), ("2008-01-02", "BBB,CCC")], columns=["date", "tickers"])
    assert overlaps_membership(pd.to_datetime(["2000-01-03"]), history, "AAA", "2016-01-01")
    assert not overlaps_membership(pd.to_datetime(["2009-01-02"]), history, "AAA", "2016-01-01")
    assert not overlaps_membership(pd.to_datetime(["2016-01-04"]), history, "BBB", "2016-01-01")


def test_sec_issuer_data_does_not_certify_candidate_ticker(db):
    rows = [{"tag": "Revenues", "unit": "USD", "start_date": "2008-01-01", "end_date": "2008-12-31",
             "val": 100, "form": "10-K", "fp": "FY", "fy": 2008, "filed_date": "2009-03-01", "accn": "example"}]
    for _ in range(2):
        historical_archive.import_sec_facts("test", "OLD", "123", rows, source_url="https://www.sec.gov/original.xml")
    assert edgar.get_edgar_facts("OLD").empty
    assert identity.resolve("OLD", "2009-03-01")["status"] == "unresolved"
    facts = edgar.get_edgar_facts("OLD", entity_id="cik:0000000123")
    assert len(facts) == 1
    assert facts.iloc[0]["filed_date"] == "2009-03-01"
    with storage.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM historical_facts").fetchone()[0] == 1
        assert conn.execute("SELECT source FROM entity_observations").fetchone()[0] == "https://www.sec.gov/original.xml"
