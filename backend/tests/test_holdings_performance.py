"""Mi cartera completa (#294): sales, dividends, daily series, returns, risk and attribution, by hand.

The portfolio (USD at 0.5 € per dollar every day):
  D1 2025-01-06  buy A 10 @ 100 USD = 500 €;  buy B 5 @ 100 € = 500 €
  D2 2025-01-07  buy C 10 @ 50 USD = 250 €
  D3 2025-01-08  sell A 5 @ 120 USD = 300 € out
  D4 2025-01-09  dividend B 20 € gross, 5 € withheld = 15 € out
Closes: A 100, 110, 120, 130 USD · B 100, 80, 95, 100 € · C —, 50, 40, 45 USD.
Values: D1 500 + 500 = 1 000 · D2 550 + 400 + 250 = 1 200 · D3 300 + 475 + 200 = 975 · D4 325 + 500 + 225 = 1 050.
"""

from datetime import date

import pandas as pd
import pytest

from gabi.domain.portfolio import holdings as rules
from gabi.domain.portfolio import holdings_performance as performance

DAYS = pd.to_datetime(["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09"])
LOTS = [
    {"id": 1, "symbol": "A", "kind": "buy", "shares": 10.0, "price": 100.0, "purchase_date": "2025-01-06",
     "currency": "USD", "commission": 0.0, "withholding": 0.0, "fx_rate": None},
    {"id": 2, "symbol": "B", "kind": "buy", "shares": 5.0, "price": 100.0, "purchase_date": "2025-01-06",
     "currency": "EUR", "commission": 0.0, "withholding": 0.0, "fx_rate": None},
    {"id": 3, "symbol": "C", "kind": "buy", "shares": 10.0, "price": 50.0, "purchase_date": "2025-01-07",
     "currency": "USD", "commission": 0.0, "withholding": 0.0, "fx_rate": None},
    {"id": 4, "symbol": "A", "kind": "sell", "shares": 5.0, "price": 120.0, "purchase_date": "2025-01-08",
     "currency": "USD", "commission": 0.0, "withholding": 0.0, "fx_rate": None},
    {"id": 5, "symbol": "B", "kind": "dividend", "shares": 0.0, "price": 20.0, "purchase_date": "2025-01-09",
     "currency": "EUR", "commission": 0.0, "withholding": 5.0, "fx_rate": None},
]
CLOSES = {"A": pd.Series([100.0, 110.0, 120.0, 130.0], index=DAYS),
          "B": pd.Series([100.0, 80.0, 95.0, 100.0], index=DAYS),
          "C": pd.Series([50.0, 40.0, 45.0], index=DAYS[1:])}
USD = pd.Series(0.5, index=DAYS)
SPY = pd.Series([100.0, 100.0, 110.0, 110.0], index=DAYS)
SECTORS = {"A": "Tecnología", "B": "Salud", "C": "Tecnología"}


def evaluate(closes=CLOSES, lots=LOTS):
    return performance.evaluate(lots, closes, {"USD": USD}, SPY, SECTORS, date(2025, 1, 9))


def test_daily_values_and_flows_by_hand():
    result = performance.history(LOTS, CLOSES, {"USD": USD}, DAYS)
    daily = result["daily"]
    assert list(daily["value_eur"]) == pytest.approx([1000.0, 1200.0, 975.0, 1050.0])
    assert list(daily["flow_eur"]) == pytest.approx([1000.0, 250.0, -300.0, -15.0])
    assert result["gaps"] == []


def test_time_weighted_and_money_weighted_returns_drawdown_and_volatility():
    portfolio = evaluate()["portfolio"]
    # Unit values: D1 1; D2 (1 200 − 250) / 1 000 = 0.95; units 1 000 + 250 / 0.95.
    units2 = 1000 + 250 / 0.95
    nav3 = (975 + 300) / units2
    units3 = units2 - 300 / nav3
    nav4 = (1050 + 15) / units3
    assert portfolio["twr"] == pytest.approx(nav4 - 1)
    # The fall: from 1 on D1 to 0.95 on D2 (−5 %), recovered on D3.
    assert portfolio["max_drawdown"] == pytest.approx(-0.05)
    assert (portfolio["peak_date"], portfolio["trough_date"], portfolio["recovered_date"]) == (
        "2025-01-06", "2025-01-07", "2025-01-08")
    returns = pd.Series([0.95 - 1, nav3 / 0.95 - 1, nav4 / nav3 - 1])
    assert portfolio["volatility"] == pytest.approx(returns.std() * 252 ** 0.5)
    assert portfolio["net_contributed_eur"] == pytest.approx(1000 + 250 - 300 - 15)
    assert portfolio["final_value_eur"] == pytest.approx(1050.0)
    assert portfolio["money_weighted"] is None and portfolio["twr_annualised"] is None  # Less than a year.


def test_money_weighted_return_over_a_year_by_hand():
    # 1 000 € on 2024-01-02, worth 1 100 € 366 days later: (1.1)^(365/366) − 1 a year.
    days = pd.to_datetime(["2024-01-02", "2025-01-02"])
    lot = {**LOTS[1], "price": 100.0, "shares": 10.0, "purchase_date": "2024-01-02"}
    result = performance.evaluate([lot], {"B": pd.Series([100.0, 110.0], index=days)}, {},
                                  pd.Series([1.0, 1.0], index=days), SECTORS, date(2025, 1, 2))
    assert result["portfolio"]["money_weighted"] == pytest.approx(1.1 ** (365 / 366) - 1, abs=1e-6)
    assert result["portfolio"]["twr"] == pytest.approx(0.10)


def test_attribution_by_position_and_sector_adds_up_to_the_total():
    attribution = evaluate()["attribution"]
    # Bought 500 + 500 + 250 = 1 250 €. Gains: A −500 + 300 + 325 = 125; B −500 + 15 + 500 = 15; C −250 + 225 = −25.
    gains = {row["symbol"]: row["gain_eur"] for row in attribution["positions"]}
    assert gains == pytest.approx({"A": 125.0, "B": 15.0, "C": -25.0})
    assert attribution["bought_eur"] == pytest.approx(1250.0)
    assert attribution["return_on_bought"] == pytest.approx(115 / 1250)
    points = {row["symbol"]: row["contribution_pp"] for row in attribution["positions"]}
    assert points == pytest.approx({"A": 10.0, "B": 1.2, "C": -2.0})
    assert sum(points.values()) == pytest.approx(attribution["return_on_bought"] * 100)
    sectors = {row["sector"]: row["contribution_pp"] for row in attribution["sectors"]}
    assert sectors == pytest.approx({"Tecnología": 8.0, "Salud": 1.2})


def test_the_sp500_receives_the_same_flows():
    spy = evaluate()["benchmark"]
    # Euro price 50, 50, 55, 55: units 20, 25, 25 − 300/55, then − 15/55.
    units = 25 - 300 / 55 - 15 / 55
    assert spy["final_value_eur"] == pytest.approx(units * 55)
    assert spy["twr"] == pytest.approx(0.10)
    assert spy["net_contributed_eur"] == pytest.approx(935.0) and spy["shortfall_eur"] == 0.0


def test_a_gap_is_listed_never_filled_and_its_flows_wait_for_the_next_session():
    closes = {**CLOSES, "C": CLOSES["C"].drop(DAYS[2])}
    result = evaluate(closes)
    assert result["gaps"] == [{"date": "2025-01-08", "symbols": ["C"]}]
    series = result["portfolio"]["series"]
    assert [point["date"] for point in series] == ["2025-01-06", "2025-01-07", "2025-01-09"]
    daily = performance.history(LOTS, closes, {"USD": USD}, DAYS)["daily"]
    assert list(daily["flow_eur"]) == pytest.approx([1000.0, 250.0, -315.0])


def test_a_movement_without_rate_blocks_the_series():
    result = performance.evaluate(LOTS, CLOSES, {}, SPY, SECTORS, date(2025, 1, 9))
    assert result["status"] == "blocked"
    assert {row["symbol"] for row in result["blocked"]} == {"A", "C"}


def test_valuation_realized_gain_and_dividends():
    histories = {"A": pd.DataFrame({"close": CLOSES["A"]}), "B": pd.DataFrame({"close": CLOSES["B"]}),
                 "C": pd.DataFrame({"close": CLOSES["C"]}), "SPY": pd.DataFrame({"close": SPY}),
                 "USDEUR=X": pd.DataFrame({"close": USD})}
    result = rules.value(LOTS, histories)
    rows = {row["symbol"]: row for row in result["positions"]}
    # A: half the cost (250 €) leaves with the sale that raised 300 €: 50 € realized; 5 shares remain.
    assert rows["A"]["shares"] == 5.0 and rows["A"]["cost_eur"] == pytest.approx(250.0)
    assert rows["A"]["realized_eur"] == pytest.approx(50.0)
    assert rows["B"]["dividends_eur"] == pytest.approx(15.0)
    assert result["totals"]["realized_eur"] == pytest.approx(50.0)
    assert result["totals"]["dividends_eur"] == pytest.approx(15.0)
    sold = [*LOTS, {**LOTS[3], "id": 6, "purchase_date": "2025-01-09"}]
    closed = rules.value(sold, histories)
    assert [row["symbol"] for row in closed["closed"]] == ["A"]
    assert closed["closed"][0]["realized_eur"] == pytest.approx(50.0 + (300.0 - 250.0))


def test_never_sell_more_than_held_nor_a_dividend_without_shares():
    rules.check_sequence(LOTS)
    with pytest.raises(ValueError, match="ese día tenías 10"):
        rules.check_sequence([*LOTS[:3], {**LOTS[3], "shares": 11.0}])
    with pytest.raises(ValueError, match="sin acciones"):
        rules.check_sequence([{**LOTS[4], "purchase_date": "2025-01-05"}, *LOTS[:4]])
    # Selling before buying, even on paper, is refused.
    with pytest.raises(ValueError):
        rules.check_sequence([{**LOTS[3], "purchase_date": "2025-01-05"}, *LOTS[:3]])


def test_movement_validation_and_csv_types():
    today = date(2025, 2, 1)
    dividend = rules.validate_lot({"symbol": "B", "kind": "dividend", "price": 20, "withholding": 5,
                                   "purchase_date": "2025-01-09", "currency": "EUR"}, today)
    assert dividend["shares"] == 0.0 and dividend["withholding"] == 5.0
    with pytest.raises(ValueError):
        rules.validate_lot({**dividend, "withholding": 25}, today)
    with pytest.raises(ValueError):
        rules.validate_lot({"symbol": "A", "kind": "sell", "shares": 1, "price": 1, "withholding": 1,
                            "purchase_date": "2025-01-09"}, today)
    csv = ("symbol;shares;price;date;currency;commission;type;withholding\n"
           "A;10;100;2025-01-06;USD;0;compra;\nA;5;120,5;2025-01-08;USD;1;venta;\nA;;3;2025-01-09;USD;;dividendo;0,45\n")
    parsed = rules.parse_csv(csv, today)
    assert [row["kind"] for row in parsed] == ["buy", "sell", "dividend"]
    assert parsed[1]["price"] == 120.5 and parsed[2]["withholding"] == 0.45


def test_api_sales_dividends_and_the_performance_view(tmp_path):
    import sqlite3
    from contextlib import closing

    from fastapi.testclient import TestClient
    from market_fixture import TODAY, seed_fixture

    from gabi.infrastructure.settings import Settings
    from gabi_api.bootstrap import create_app

    seed_fixture(tmp_path)
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db, db:
        db.execute("INSERT INTO prices(symbol,date,close,adj_close) SELECT 'USDEUR=X',date,0.9,0.9 FROM prices "
                   "WHERE symbol='SPY'")
    buy = {"symbol": "T000", "shares": 10, "price": 100, "purchase_date": "2026-06-01", "currency": "EUR"}
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        assert api.get("/api/v1/portfolio/holdings/performance").status_code == 404
        bought = api.post("/api/v1/portfolio/holdings", json=buy).json()
        too_many = api.post("/api/v1/portfolio/holdings", json=buy | {"kind": "sell", "shares": 11,
                                                                      "purchase_date": "2026-07-01"})
        assert too_many.status_code == 422 and "tenías 10" in too_many.json()["error"]["message"]
        assert api.post("/api/v1/portfolio/holdings", json=buy | {"kind": "sell", "shares": 4,
                                                                  "purchase_date": "2026-07-01"}).status_code == 201
        assert api.post("/api/v1/portfolio/holdings", json={
            "symbol": "T000", "kind": "dividend", "price": 12, "withholding": 2, "purchase_date": "2026-08-03",
            "currency": "EUR"}).status_code == 201
        # Deleting the purchase would leave the sale and the dividend without shares.
        refused = api.post(f"/api/v1/portfolio/holdings/{bought['id']}/delete")
        assert refused.status_code == 422 and "No se puede borrar" in refused.json()["error"]["message"]
        summary = api.get("/api/v1/portfolio/holdings").json()
        assert summary["positions"][0]["shares"] == 6 and summary["totals"]["dividends_eur"] == 10
        result = api.get("/api/v1/portfolio/holdings/performance").json()
        assert result["status"] == "ok" and result["benchmark"]["status"] == "ok"
        # 1 000 € bought, 4 × 100 € sold, 12 − 2 = 10 € of dividends.
        assert result["portfolio"]["net_contributed_eur"] == pytest.approx(590.0)
        assert result["attribution"]["bought_eur"] == pytest.approx(1000.0)
        assert result["portfolio"]["series"][0]["date"] == "2026-06-01"
    # A table created before #294 gains its columns on the next write; its rows are purchases.
    old = tmp_path / "old"
    old.mkdir()
    with closing(sqlite3.connect(old / "gabi.db")) as db, db:
        db.execute("CREATE TABLE portfolio_holdings (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, "
                   "shares REAL NOT NULL, price REAL NOT NULL, purchase_date TEXT NOT NULL, currency TEXT NOT NULL, "
                   "commission REAL NOT NULL DEFAULT 0, fx_rate REAL, note TEXT, created_at TEXT NOT NULL, "
                   "updated_at TEXT NOT NULL)")
        db.execute("INSERT INTO portfolio_holdings(symbol,shares,price,purchase_date,currency,created_at,updated_at)"
                   " VALUES('T000',3,10,'2026-06-01','EUR','x','x')")
    from gabi.infrastructure.storage.holdings import SqliteHoldings

    store = SqliteHoldings(old)
    assert store.lots()[0]["kind"] == "buy"
    store.add([rules.validate_lot(buy | {"kind": "sell", "shares": 1, "purchase_date": "2026-06-02"}, TODAY)], "now")
    assert [row["kind"] for row in store.lots()] == ["buy", "sell"]
