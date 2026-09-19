import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, sim_portfolios, storage


def _seed(symbol, dates, closes):
    df = pd.DataFrame({
        "Open": closes, "High": closes, "Low": closes, "Close": closes,
        "Adj Close": closes, "Volume": [1000] * len(closes),
    }, index=pd.to_datetime(dates))
    storage.upsert_prices(symbol, df)


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")


def test_multiple_portfolios_and_dated_trades_are_isolated(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-05", "2024-01-08", "2024-01-09"], [100, 110, 120])
    _seed("SPY", ["2024-01-05", "2024-01-08", "2024-01-09"], [100, 101, 102])
    first = sim_portfolios.create_portfolio("Estrategia A", 1000, spread_bps=100)
    second = sim_portfolios.create_portfolio("Estrategia B", 1000)
    buy = sim_portfolios.add_trade(first, "AAA", "STOCK", "BUY", "2024-01-06", 500)
    assert buy["execution_date"] == "2024-01-08"  # sábado -> siguiente sesión
    assert buy["commission"] == 1
    assert sim_portfolios.list_trades(second).empty
    sim_portfolios.add_trade(first, "AAA", "STOCK", "SELL", "2024-01-09", 100)
    result = sim_portfolios.portfolio_history(first)
    summary = sim_portfolios.summarize(result)
    assert len(result["trades"]) == 2
    assert result["cash"] > 500
    assert summary["status"] == "complete"
    assert summary["benchmark_return"] is not None


def test_backdated_trade_cannot_overdraw_later_buy(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-05", "2024-01-08"], [100, 100])
    portfolio_id = sim_portfolios.create_portfolio("A", 1000)
    sim_portfolios.add_trade(portfolio_id, "AAA", "STOCK", "BUY", "2024-01-08", 900)
    with pytest.raises(ValueError, match="Efectivo insuficiente"):
        sim_portfolios.add_trade(portfolio_id, "AAA", "STOCK", "BUY", "2024-01-05", 200)
    assert len(sim_portfolios.list_trades(portfolio_id)) == 1


def test_cannot_sell_more_than_held(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-05"], [100])
    portfolio_id = sim_portfolios.create_portfolio("A", 1000)
    with pytest.raises(ValueError, match="Posición insuficiente"):
        sim_portfolios.add_trade(portfolio_id, "AAA", "STOCK", "SELL", "2024-01-05", 100)


def test_spread_and_commission_reduce_portfolio_value(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-05"], [100])
    portfolio_id = sim_portfolios.create_portfolio("A", 1000, stock_commission=1, spread_bps=100)
    sim_portfolios.add_trade(portfolio_id, "AAA", "STOCK", "BUY", "2024-01-05", 500)
    result = sim_portfolios.portfolio_history(portfolio_id)
    expected = 499 + 500 / 1.005
    assert result["curve"]["value"].iloc[-1] == pytest.approx(expected)


def test_missing_first_session_quote_cannot_be_replaced_by_later_price(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-09"], [100])
    with pytest.raises(ValueError, match="primera sesión bursátil"):
        sim_portfolios.execution_quote("AAA", "2024-01-06")


def test_exchange_holiday_executes_on_next_session(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-02"], [100])
    quote = sim_portfolios.execution_quote("AAA", "2024-01-01")
    assert quote["date"] == "2024-01-02"


def test_eur_portfolio_applies_trade_fx_and_conversion_cost(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    _seed("AAA", ["2024-01-05"], [100])
    _seed("USDEUR=X", ["2024-01-05"], [.9])
    portfolio_id = sim_portfolios.create_portfolio("EUR", 1000, base_currency="EUR")
    trade = sim_portfolios.add_trade(portfolio_id, "AAA", "STOCK", "BUY", "2024-01-05", 500,
                                     fx_rate=.9, fx_fee_bps=100, commission=2, spread_bps=0)
    assert trade["fx_rate"] == .9
    result = sim_portfolios.portfolio_history(portfolio_id)
    assert result["cash"] == pytest.approx(1000 - 502 * .9 * 1.01)
    assert result["curve"]["value"].iloc[-1] == pytest.approx(result["cash"] + 500 * .9)


def test_european_holiday_calendar_differs_from_nyse(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    _seed("AAA.DE", ["2024-05-02"], [100])
    quote = sim_portfolios.execution_quote("AAA.DE", "2024-05-01", market="XETR")
    assert quote["date"] == "2024-05-02"


def test_existing_portfolio_database_is_migrated_without_losing_trades(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    with sqlite3.connect(config.DB_PATH) as conn:
        conn.executescript("""
        CREATE TABLE sim_portfolios (id INTEGER PRIMARY KEY, name TEXT UNIQUE, initial_cash REAL,
            stock_commission REAL, etf_commission REAL, spread_bps REAL, created_at TEXT);
        CREATE TABLE sim_trades (id INTEGER PRIMARY KEY, portfolio_id INTEGER, symbol TEXT,
            asset_type TEXT, side TEXT, requested_date TEXT, execution_date TEXT,
            reference_close REAL, notional REAL, commission REAL, spread_bps REAL, created_at TEXT);
        INSERT INTO sim_portfolios VALUES (1,'Anterior',1000,1,0,10,'2024-01-01');
        INSERT INTO sim_trades VALUES (1,1,'AAA','STOCK','BUY','2024-01-05','2024-01-05',100,100,1,10,'2024-01-05');
        """)
    assert sim_portfolios.get_portfolio(1)["base_currency"] == "USD"
    trades = sim_portfolios.list_trades(1)
    assert len(trades) == 1
    assert trades.iloc[0]["market"] == "XNYS"
    assert trades.iloc[0]["quote_currency"] == "USD"


def test_sma_backtest_runs_on_cached_prices(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    dates = pd.date_range("2024-01-01", periods=150, freq="B")
    closes = [100 + i * .03 + 4 * ((i // 15) % 2) for i in range(150)]
    _seed("AAA", dates, closes)
    result = sim_portfolios.sma_backtest("AAA", "2024-01-01", "2024-12-31", 10, 30,
                                         10000, 1, 10)
    assert "strategy_return" in result
    assert len(result["equity_curve"]) == 150
