import sqlite3
from datetime import date

import pandas as pd
import pytest

from gabi import config, storage
from gabi.application.errors import QueryError
from gabi.application.portfolio.simulations import Simulations
from gabi.domain.portfolio.simulation import execution_quote
from gabi.infrastructure.storage.simulations import SqliteSimulations

TODAY = date(2024, 12, 31)


def _seed(symbol, dates, closes):
    df = pd.DataFrame({
        "Open": closes, "High": closes, "Low": closes, "Close": closes,
        "Adj Close": closes, "Volume": [1000] * len(closes),
    }, index=pd.to_datetime(dates))
    storage.upsert_prices(symbol, df)


def _app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    return Simulations(SqliteSimulations(tmp_path), lambda: TODAY)


def _create(app, name, initial_cash, **costs):
    payload = {"name": name, "initial_cash": initial_cash, "stock_commission": 1.0, "etf_commission": 0.0,
               "spread_bps": 10.0, "base_currency": "USD"} | costs
    return app.create(payload)["id"]


def _trade(app, portfolio_id, symbol, side, requested_date, notional, **options):
    payload = {"symbol": symbol, "asset_type": "STOCK", "side": side, "requested_date": date.fromisoformat(requested_date),
               "notional": notional, "market": "XNYS", "quote_currency": "USD", "commission": None,
               "spread_bps": None, "fx_rate": None, "fx_fee_bps": 0.0} | options
    return app.trade(portfolio_id, payload)


def test_multiple_portfolios_and_dated_trades_are_isolated(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-05", "2024-01-08", "2024-01-09"], [100, 110, 120])
    _seed("SPY", ["2024-01-05", "2024-01-08", "2024-01-09"], [100, 101, 102])
    first = _create(app, "Estrategia A", 1000, spread_bps=100)
    second = _create(app, "Estrategia B", 1000)
    buy = _trade(app, first, "AAA", "BUY", "2024-01-06", 500)
    assert buy["execution_date"] == "2024-01-08"  # sábado -> siguiente sesión
    assert buy["commission"] == 1
    assert app.trades(second) == []
    _trade(app, first, "AAA", "SELL", "2024-01-09", 100)
    result = app.result(first)
    assert len(app.trades(first)) == 2
    assert result["cash"] > 500
    assert result["summary"]["status"] == "complete"
    assert result["summary"]["benchmark_return"] is not None


def test_backdated_trade_cannot_overdraw_later_buy(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-05", "2024-01-08"], [100, 100])
    portfolio_id = _create(app, "A", 1000)
    _trade(app, portfolio_id, "AAA", "BUY", "2024-01-08", 900)
    with pytest.raises(QueryError, match="Efectivo insuficiente"):
        _trade(app, portfolio_id, "AAA", "BUY", "2024-01-05", 200)
    assert len(app.trades(portfolio_id)) == 1


def test_cannot_sell_more_than_held(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-05"], [100])
    portfolio_id = _create(app, "A", 1000)
    with pytest.raises(QueryError, match="Posición insuficiente"):
        _trade(app, portfolio_id, "AAA", "SELL", "2024-01-05", 100)


def test_spread_and_commission_reduce_portfolio_value(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-05"], [100])
    portfolio_id = _create(app, "A", 1000, stock_commission=1, spread_bps=100)
    _trade(app, portfolio_id, "AAA", "BUY", "2024-01-05", 500)
    curve = app.result(portfolio_id)["curve"]
    assert curve[-1]["value"] == pytest.approx(499 + 500 / 1.005)


def test_missing_first_session_quote_cannot_be_replaced_by_later_price(tmp_path, monkeypatch):
    _app(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-09"], [100])
    with pytest.raises(ValueError, match="primera sesión bursátil"):
        execution_quote(storage.get_prices("AAA"), "2024-01-06", "XNYS", TODAY)


def test_exchange_holiday_executes_on_next_session(tmp_path, monkeypatch):
    _app(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-02"], [100])
    assert execution_quote(storage.get_prices("AAA"), "2024-01-01", "XNYS", TODAY)["date"] == "2024-01-02"


def test_eur_portfolio_applies_trade_fx_and_conversion_cost(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-05"], [100])
    _seed("USDEUR=X", ["2024-01-05"], [.9])
    portfolio_id = _create(app, "EUR", 1000, base_currency="EUR")
    trade = _trade(app, portfolio_id, "AAA", "BUY", "2024-01-05", 500,
                   fx_rate=.9, fx_fee_bps=100, commission=2, spread_bps=0)
    assert trade["fx_rate"] == .9
    result = app.result(portfolio_id)
    assert result["cash"] == pytest.approx(1000 - 502 * .9 * 1.01)
    assert result["curve"][-1]["value"] == pytest.approx(result["cash"] + 500 * .9)


def test_european_holiday_calendar_differs_from_nyse(tmp_path, monkeypatch):
    _app(tmp_path, monkeypatch)
    _seed("AAA.DE", ["2024-05-02"], [100])
    assert execution_quote(storage.get_prices("AAA.DE"), "2024-05-01", "XETR", TODAY)["date"] == "2024-05-02"


def test_existing_portfolio_database_is_read_with_defaults_without_writing(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch)
    with sqlite3.connect(tmp_path / "gabi.db") as conn:
        conn.executescript("""
        CREATE TABLE sim_portfolios (id INTEGER PRIMARY KEY, name TEXT UNIQUE, initial_cash REAL,
            stock_commission REAL, etf_commission REAL, spread_bps REAL, created_at TEXT);
        CREATE TABLE sim_trades (id INTEGER PRIMARY KEY, portfolio_id INTEGER, symbol TEXT,
            asset_type TEXT, side TEXT, requested_date TEXT, execution_date TEXT,
            reference_close REAL, notional REAL, commission REAL, spread_bps REAL, created_at TEXT);
        INSERT INTO sim_portfolios VALUES (1,'Anterior',1000,1,0,10,'2024-01-01');
        INSERT INTO sim_trades VALUES (1,1,'AAA','STOCK','BUY','2024-01-05','2024-01-05',100,100,1,10,'2024-01-05');
        """)
    before = (tmp_path / "gabi.db").read_bytes()
    assert app.portfolio(1)["base_currency"] == "USD"
    trades = app.trades(1)
    assert len(trades) == 1
    assert trades[0]["market"] == "XNYS"
    assert trades[0]["quote_currency"] == "USD"
    assert (tmp_path / "gabi.db").read_bytes() == before
