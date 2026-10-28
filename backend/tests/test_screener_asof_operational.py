"""Opt-in operational mode of the historical ranking for live signals (#237), offline and temporary."""

import pandas as pd
import pytest

from gabi import config, edgar, identity, screener_asof, storage

DAY = "2026-10-22"


@pytest.fixture(autouse=True)
def offline_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")

    def no_network(*args, **kwargs):
        pytest.fail("The ranking must be offline")

    monkeypatch.setattr("requests.sessions.Session.request", no_network)
    monkeypatch.setattr("socket.create_connection", no_network)


def _prices(symbol, last=DAY, sessions=300):
    days = pd.bdate_range(end=last, periods=sessions)
    close = pd.Series(range(100, 100 + sessions), index=days, dtype=float)
    frame = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Adj Close": close,
                          "Volume": 1000.0})
    storage.upsert_prices(symbol, frame)


def _facts():
    rows = []
    for year in (2022, 2023, 2024, 2025):
        filed = f"{year + 1}-02-15"
        for tag, value in (("Revenues", 1000.0 * (year - 2020)), ("NetIncomeLoss", 100.0 * (year - 2020))):
            rows.append({"tag": tag, "unit": "USD", "start_date": f"{year}-01-01", "end_date": f"{year}-12-31",
                         "val": value, "form": "10-K", "fp": "FY", "fy": year, "filed_date": filed, "accn": f"a{year}"})
        rows.append({"tag": "EntityCommonStockSharesOutstanding", "unit": "shares", "start_date": "",
                     "end_date": f"{year}-12-31", "val": 10.0, "form": "10-K", "fp": "FY", "fy": year,
                     "filed_date": filed, "accn": f"a{year}"})
    return rows


@pytest.fixture
def market():
    _prices("SPY")
    _prices("AAA")
    # The issuer's history was stored under its former ticker (#201); a one-day universe snapshot
    # gives AAA an alias that does not cover the signal, as in production.
    edgar.upsert_edgar_facts("OLDA", _facts(), cik="1")
    identity.add_alias(identity.ensure_entity("1"), "AAA", "2026-10-28", "2026-10-29", source="observed-universe-snapshot")


def test_default_path_reads_the_ticker_and_misses_history_stored_under_another_alias(market):
    # A universe snapshot does not block the ticker cache; fundamentals by symbol miss the issuer's
    # rows stored under its former ticker, which is why the live mode reads by issuer.
    row = screener_asof.build_ranking_as_of(DAY, symbols=["AAA"])["table"].loc["AAA"]
    assert row["identity_status"] == "unresolved" and row["entity_id"] is None
    assert row["price"] == pytest.approx(399.0) and pd.isna(row["ps"])


def test_operational_mode_reads_issuer_fundamentals_and_ticker_prices(market):
    table = screener_asof.build_ranking_as_of(DAY, symbols=["AAA"],
                                              operational_entities={"AAA": "cik:0000000001"})["table"]
    row = table.loc["AAA"]
    assert row["entity_id"] == "cik:0000000001" and row["identity_source"] == "sec_cik_map"
    assert row["price"] == pytest.approx(399.0) and row["market_cap"] == pytest.approx(3990.0)
    assert row["ps"] == pytest.approx(3990.0 / 5000.0)  # revenue of the issuer, stored under OLDA
    assert row["momentum_12m"] is not None and row["volatility"] is not None


def test_operational_mode_requires_explicit_symbols_outside_the_accredited_layer(market):
    with pytest.raises(ValueError, match="operativo"):
        screener_asof.build_ranking_as_of(DAY, operational_entities={})
    with pytest.raises(ValueError, match="operativo"):
        screener_asof.build_ranking_as_of("2012-06-29", symbols=["AAA"], operational_entities={})
