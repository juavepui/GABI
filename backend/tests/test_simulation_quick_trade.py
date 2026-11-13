"""Carteras simuladas (#192): a US buy takes three fields; market and currency follow the ticker."""

import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError
from gabi.application.portfolio.sim_prices import refresh_prices
from gabi.domain.portfolio.simulation import fx_symbol, listing
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def test_the_ticker_suffix_gives_market_and_currency():
    assert listing(" aapl ") == ("AAPL", "XNYS", "USD")
    assert listing("brk.b") == ("BRK-B", "XNYS", "USD")  # A US share class, not a market.
    assert listing("SAP.DE") == ("SAP.DE", "XETR", "EUR")
    assert listing("bp.l") == ("BP.L", "XLON", "GBP")
    assert listing("SAN.MC") == ("SAN.MC", "XMAD", "EUR")
    assert listing("MC.PA") == ("MC.PA", "XPAR", "EUR")
    for wrong in ("", "../X", "A" * 21):
        with pytest.raises(ValueError):
            listing(wrong)


def test_the_explicit_price_download_takes_the_ticker_as_typed_and_stores_it_as_a_trade_does():
    JobCommand("sim_prices", portfolio_id=1, symbols=("SAP.DE",))
    JobCommand("sim_prices", portfolio_id=1, symbols=("BRK.B",))
    with pytest.raises(QueryError):
        JobCommand("sim_prices", portfolio_id=1, symbols=("../X",))
    portfolio = {"base_currency": "USD"}
    store = type("Store", (), {"portfolio": lambda self, _: portfolio, "trades": lambda self, _: []})()
    fetched = []
    refresh_prices(store, 1, "brk.b", fx_symbol, lambda symbols: fetched.extend(symbols) or {})
    assert fetched[:2] == ["BRK-B", "SPY"]


def _new(api, **body) -> int:
    created = api.post("/api/v1/portfolio/simulations", json={"name": "Rápida", "initial_cash": 10000} | body)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_three_fields_register_a_us_buy_and_a_suffix_a_european_one(tmp_path):
    seed_fixture(tmp_path)
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db, db:
        for symbol, close in (("SAP.DE", 200.0), ("EURUSD=X", 1.1)):
            db.execute("INSERT INTO prices(symbol,date,close,adj_close) VALUES(?,?,?,?)",
                       (symbol, "2026-09-28", close, close))
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        portfolio = _new(api)
        quick = api.post(f"/api/v1/portfolio/simulations/{portfolio}/trades",
                         json={"symbol": "T000", "requested_date": "2026-09-28", "notional": 1000})
        assert quick.status_code == 201, quick.text
        trade = quick.json()
        assert (trade["side"], trade["asset_type"], trade["market"], trade["quote_currency"]) == (
            "BUY", "STOCK", "XNYS", "USD")
        assert trade["commission"] == 1 and trade["fx_rate"] == 1  # The portfolio's own costs.
        european = api.post(f"/api/v1/portfolio/simulations/{portfolio}/trades",
                            json={"symbol": "sap.de", "requested_date": "2026-09-28", "notional": 500})
        assert european.status_code == 201, european.text
        body = european.json()
        assert (body["symbol"], body["market"], body["quote_currency"]) == ("SAP.DE", "XETR", "EUR")
        assert body["fx_rate"] == pytest.approx(1.1)  # The cached EURUSD close of that session.
        # A market typed in «Opciones avanzadas» still wins over the inferred one.
        typed = api.post(f"/api/v1/portfolio/simulations/{portfolio}/trades",
                         json={"symbol": "T001", "requested_date": "2026-09-28", "notional": 100,
                               "market": "XNYS", "quote_currency": "USD", "side": "BUY"})
        assert typed.status_code == 201, typed.text
        missing = api.post(f"/api/v1/portfolio/simulations/{portfolio}/trades",
                           json={"symbol": "NOPRICE", "requested_date": "2026-09-28", "notional": 100})
        assert missing.status_code == 422
        assert missing.json()["error"]["code"] == "prices_missing"
        assert "NOPRICE" in missing.json()["error"]["message"]
