"""Mi cartera (#181): explicit writes, CSV import, valuation in euros against SPY and the plan from saved lots."""

import sqlite3
from contextlib import closing
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.application.portfolio.holdings import refresh_prices
from gabi.domain.market import model_policy
from gabi.domain.portfolio import holdings as rules
from gabi.domain.portfolio import selection
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.holdings import SqliteHoldings
from gabi_api.bootstrap import create_app

LOT = {"symbol": "T000", "shares": 10, "price": 100, "purchase_date": "2026-06-01", "currency": "USD",
       "commission": 1, "fx_rate": 0.9}


def _closes(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({"close": list(values.values())}, index=pd.to_datetime(list(values)))


def _lot(**changes) -> dict:
    return rules.validate_lot(LOT | changes, TODAY)


def test_valuation_converts_with_the_rates_of_each_date_and_buys_spy_with_the_same_euros():
    lots = [_lot(symbol="AAA", purchase_date="2026-01-05"),
            _lot(symbol="BBB", shares=5, price=50, commission=0, currency="EUR", purchase_date="2026-01-05")]
    histories = {"AAA": _closes({"2026-01-05": 100, "2026-03-02": 120}),
                 "BBB": _closes({"2026-01-05": 50, "2026-03-02": 60}),
                 "SPY": _closes({"2026-01-05": 500, "2026-03-02": 550}),
                 "USDEUR=X": _closes({"2026-01-05": 0.9, "2026-03-02": 0.8})}
    result = rules.value(lots, histories)
    rows = {row["symbol"]: row for row in result["positions"]}
    aaa, bbb = rows["AAA"], rows["BBB"]
    assert aaa["cost"] == 1001 and aaa["value"] == 1200 and aaa["price_date"] == "2026-03-02"
    assert aaa["price_return"] == pytest.approx(1200 / 1001 - 1)
    assert aaa["cost_eur"] == pytest.approx(1001 * 0.9) and aaa["value_eur"] == pytest.approx(1200 * 0.8)
    assert aaa["spy_return_usd"] == pytest.approx(0.1)
    # The euros spent buy SPY at the dollar rate of that day and are valued at today's rate.
    assert aaa["spy_value_eur"] == pytest.approx(1001 * 0.9 / (500 * 0.9) * 550 * 0.8)
    assert bbb["value_eur"] == 300 and bbb["return_eur"] == pytest.approx(0.2) and bbb["spy_return_usd"] is None
    assert bbb["spy_value_eur"] == pytest.approx(250 / (500 * 0.9) * 550 * 0.8)
    totals = result["totals"]
    assert totals["complete"] and totals["value_eur"] == pytest.approx(960 + 300)
    assert totals["return_eur"] == pytest.approx((960 + 300) / (900.9 + 250) - 1)
    assert totals["spy_return_eur"] == pytest.approx(550 * 0.8 / (500 * 0.9) - 1)
    assert sum(row["weight_pct"] for row in rows.values()) == pytest.approx(100)


def test_a_missing_rate_or_price_is_reported_and_never_filled_in():
    lots = [_lot(symbol="AAA", purchase_date="2026-01-05"),
            _lot(symbol="GBX", currency="GBP", fx_rate=1.15, purchase_date="2026-01-05"),
            _lot(symbol="NOPRICE", purchase_date="2026-01-05")]
    histories = {"AAA": _closes({"2026-01-05": 100}), "GBX": _closes({"2026-01-05": 100}),
                 "SPY": _closes({"2026-01-05": 500})}
    rows = {row["symbol"]: row for row in rules.value(lots, histories)["positions"]}
    assert rows["AAA"]["status"] == "missing_fx" and rows["AAA"]["value"] == 1000  # Own currency still shown.
    assert rows["GBX"]["cost_eur"] == pytest.approx(1001 * 1.15)  # The broker's rate, recorded with the lot.
    assert rows["GBX"]["status"] == "missing_fx"  # No cached GBP rate for today.
    assert rows["NOPRICE"]["status"] == "missing_price" and rows["NOPRICE"]["value"] is None
    assert rules.value(lots, histories)["totals"]["complete"] is False
    assert rules.price_symbols(lots) == ["AAA", "GBX", "NOPRICE", "SPY", "GBPEUR=X", "USDEUR=X"]


def test_csv_import_accepts_commas_or_semicolons_and_rejects_the_whole_file_on_one_bad_row():
    lots = rules.parse_csv("symbol,shares,price,date,currency,commission\nbrk.b,2,400.5,2026-05-04,USD,1\n"
                           "SAN,100,4.2,2026-05-04,EUR,\n", TODAY)
    assert [(lot["symbol"], lot["shares"], lot["price"], lot["commission"]) for lot in lots] == [
        ("BRK-B", 2, 400.5, 1), ("SAN", 100, 4.2, 0)]
    semicolon = rules.parse_csv("Symbol;Shares;Price;Date;Currency;Commission\nAAPL;1,5;1.234,5;2026-05-04;USD;1\n",
                                TODAY)
    assert (semicolon[0]["shares"], semicolon[0]["price"]) == (1.5, 1234.5)
    with pytest.raises(ValueError, match="línea 3"):
        rules.parse_csv("symbol,shares,price,date\nAAPL,1,100,2026-05-04\nMSFT,-1,100,2026-05-04\n", TODAY)
    with pytest.raises(ValueError, match="Faltan columnas: price"):
        rules.parse_csv("symbol,shares,date\nAAPL,1,2026-05-04\n", TODAY)
    with pytest.raises(ValueError, match="futura"):
        rules.validate_lot(LOT | {"purchase_date": "2026-09-30"}, TODAY)


def test_holdings_survive_a_restart_and_are_edited_only_by_explicit_writes(tmp_path):
    seed_fixture(tmp_path)
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db, db:
        db.execute("INSERT INTO prices(symbol,date,close,adj_close) VALUES('USDEUR=X',?,0.9,0.9)",
                   (TODAY.isoformat(),))
    stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        empty = api.get("/api/v1/portfolio/holdings").json()
        assert empty["positions"] == [] and empty["totals"] is None
        assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp  # A GET never creates the table.
        created = api.post("/api/v1/portfolio/holdings", json=LOT)
        assert created.status_code == 201, created.text
        lot_id = created.json()["id"]
        assert api.post("/api/v1/portfolio/holdings", json=LOT | {"currency": "EUR"}).json()["error"]["code"] \
            == "currency_mismatch"
        assert api.post("/api/v1/portfolio/holdings", json=LOT | {"purchase_date": "2026-09-30"}).status_code == 422
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:  # A restart keeps them.
        assert [row["id"] for row in api.get("/api/v1/portfolio/holdings/lots").json()["items"]] == [lot_id]
        edited = api.post(f"/api/v1/portfolio/holdings/{lot_id}", json=LOT | {"shares": 12})
        assert edited.json()["shares"] == 12
        summary = api.get("/api/v1/portfolio/holdings").json()
        position = summary["positions"][0]
        assert position["symbol"] == "T000" and position["shares"] == 12 and position["status"] == "ok"
        assert position["in_target"] in (True, False) and position["sector"] == "Information Technology"
        assert summary["totals"]["complete"] and summary["deviations"][0]["target_pct"] >= 0
        assert any(row["symbol"] == "T000" for row in summary["deviations"])
        imported = api.post("/api/v1/portfolio/holdings/import",
                            json={"csv": "symbol,shares,price,date\nT001,1,50,2026-07-01\nT002,0,1,2026-07-01\n"})
        assert imported.status_code == 422 and "línea 3" in imported.json()["error"]["message"]
        assert len(api.get("/api/v1/portfolio/holdings/lots").json()["items"]) == 1  # Nothing was written.
        assert api.post("/api/v1/portfolio/holdings/import", json={
            "csv": "symbol,shares,price,date\nT001,1,50,2026-07-01\n"}).json()["imported"] == 1
        assert api.post(f"/api/v1/portfolio/holdings/{lot_id}/delete").json() == {"deleted": True}
        assert api.post(f"/api/v1/portfolio/holdings/{lot_id}/delete").status_code == 404
        assert [row["symbol"] for row in api.get("/api/v1/portfolio/holdings/lots").json()["items"]] == ["T001"]


def test_the_plan_starts_from_saved_holdings_unless_a_what_if_is_typed(tmp_path):
    seed_fixture(tmp_path)
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db, db:
        db.execute("INSERT INTO prices(symbol,date,close,adj_close) VALUES('USDEUR=X',?,0.5,0.5)",
                   (TODAY.isoformat(),))
        price = db.execute("SELECT close FROM prices WHERE symbol='T000' ORDER BY date DESC LIMIT 1").fetchone()[0]
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as api:
        api.post("/api/v1/portfolio/holdings", json=LOT | {"shares": 2})
        api.post("/api/v1/portfolio/holdings", json=LOT | {"symbol": "NODATA"})
        saved = api.post("/api/v1/portfolio/plan", json={"n_positions": 5, "new_capital_eur": 200,
                                                         "use_saved_holdings": True}).json()
        typed = api.post("/api/v1/portfolio/plan", json={"n_positions": 5, "new_capital_eur": 200,
                                                         "use_saved_holdings": True,
                                                         "holdings_text": "T001,10"}).json()
        snapshot = app.state.market.repository.ranking(dict(model_policy.FROZEN_WEIGHTS), TODAY)
    target = selection.target_portfolio(snapshot.table, 5)
    expected = selection.allocate_new_capital(target, {"T000": 2 * price * 0.5}, 200)
    assert saved["holdings_source"] == "saved" and saved["holdings_unvalued"] == ["NODATA"]
    assert saved["allocations"] == [{"symbol": item["symbol"], "name": item["name"], "amount_eur": item["amount"]}
                                    for item in expected["allocations"]]
    assert typed["holdings_source"] == "text" and typed["holdings_unvalued"] == []


def test_the_explicit_price_action_downloads_holdings_spy_and_rates(tmp_path):
    store = SqliteHoldings(tmp_path)
    with pytest.raises(Exception, match="no tiene compras"):
        refresh_prices(store, lambda symbols: {})
    store.add([_lot(), _lot(symbol="SAN", currency="EUR")], "2026-09-29T00:00:00+00:00")
    asked = []
    result = refresh_prices(store, lambda symbols: asked.append(symbols) or {"SAN": "sin datos"})
    assert asked == [["T000", "SAN", "SPY", "USDEUR=X"]]
    assert result == {"kind": "holdings_prices", "symbols": asked[0], "updated": 3, "failed": {"SAN": "sin datos"}}
    assert date.fromisoformat(store.lots()[0]["purchase_date"]) == date(2026, 6, 1)
