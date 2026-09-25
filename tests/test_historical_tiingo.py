import json

import pandas as pd
import pytest

from gabi import config, historical_archive, historical_tiingo, storage
from gabi.historical_price_audit import choose_source


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(historical_tiingo, "DIRECTORY", tmp_path / "tiingo")
    monkeypatch.setattr("requests.sessions.Session.request",
                        lambda *args, **kwargs: pytest.fail("No network allowed"))
    storage.init_db()


def test_only_current_listings_that_already_covered_the_period_are_fetched():
    listings = pd.DataFrame({"assetType": ["Stock", "ETF", "Stock"], "startDate": ["1988-01-04", "2023-05-15",
                                                                                   "2025-02-24"],
                             "endDate": ["2026-09-24", "2026-09-24", "2026-09-24"]},
                            index=["APD", "EMC", "SNDK"])
    assert historical_tiingo.eligible(listings, "APD", "2009-03-31", "2015-12-31")
    # Recycled tickers: the API would return the new owner (an ETF, a 2025 spin-off).
    assert not historical_tiingo.eligible(listings, "EMC", "2009-03-31", "2015-12-31")
    assert not historical_tiingo.eligible(listings, "SNDK", "2009-03-31", "2015-12-31")
    assert not historical_tiingo.eligible(listings, "MISSING", "2009-03-31", "2015-12-31")


def test_cached_responses_import_idempotently_as_as_traded_archive(db):
    historical_tiingo.DIRECTORY.mkdir(parents=True)
    rows = [{"date": "2012-11-07T00:00:00.000Z", "open": 78.9, "high": 79.8, "low": 78.6, "close": 79.46,
             "adjClose": 51.73, "volume": 1935100, "divCash": 0.0, "splitFactor": 1.0},
            {"date": "2012-11-08T00:00:00.000Z", "open": 79.4, "high": 80.1, "low": 79.0, "close": 79.15,
             "adjClose": 51.53, "volume": 2135200, "divCash": 0.0, "splitFactor": 1.0}]
    (historical_tiingo.DIRECTORY / "APD.json").write_text(json.dumps(rows), encoding="utf-8")
    assert historical_tiingo.import_cached()["accepted"] == 2
    historical_tiingo.import_cached()
    prices = historical_archive.get_prices(historical_tiingo.SOURCE_ID, "APD", "2012-01-01", "2013-01-01")
    assert len(prices) == 2 and prices.iloc[0].close == 79.46 and prices.iloc[0].adj_close == 51.73
    assert prices.iloc[0].close_basis == "as_traded"


def test_tiingo_fallback_is_named_and_needs_the_same_sec_evidence():
    complete = {"complete": True, "first": "2012-01-03", "last": "2012-12-31"}
    issuer = {"listing": None, "yahoo_level": "missing", "archive_level": "passed",
              "archive_adjustment": "dividends_reconciled"}
    proof = {"first_trade": "2001-01-01", "last_trade": "2014-01-01", "boundary_evidence": [{}],
             "adjustment_basis": "split_and_dividend_adjusted", "adjustment_evidence": [{}],
             "corporate_action_evidence": [{}]}
    assert choose_source("corroborated_candidate", False, {"complete": False}, complete, "insufficient_overlap",
                         issuer=issuer, fallback_proof=proof, archive_name="tiingo") == (
        "tiingo", "fallback_accredited")
    assert choose_source("corroborated_candidate", False, {"complete": False}, complete, "insufficient_overlap",
                         issuer={**issuer, "archive_level": "failed"}, fallback_proof=proof,
                         archive_name="tiingo") == (None, "price_level_failed")


def test_wiki_cache_imports_as_traded_rows_without_storing_the_key(db, monkeypatch):
    from gabi import historical_wiki
    monkeypatch.setattr(historical_wiki, "DIRECTORY", historical_tiingo.DIRECTORY.parent / "wiki")
    historical_wiki.DIRECTORY.mkdir(parents=True)
    columns = ["ticker", "date", "open", "high", "low", "close", "volume", "ex-dividend", "split_ratio", "adj_close"]
    payload = {"columns": columns, "data": [["EMC", "2012-11-07", 24.91, 25.17, 24.38, 24.54, 21609000.0, 0.0,
                                             1.0, 23.23]]}
    (historical_wiki.DIRECTORY / "EMC.json").write_text(json.dumps(payload), encoding="utf-8")
    assert historical_wiki.import_cached()["accepted"] == 1
    prices = historical_archive.get_prices(historical_wiki.SOURCE_ID, "EMC", "2012-01-01", "2013-01-01")
    assert prices.iloc[0].close == 24.54 and prices.iloc[0].adj_close == 23.23
    assert historical_wiki._wiki_ticker("BRK-B") == "BRK_B"
