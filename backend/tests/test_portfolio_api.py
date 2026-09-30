"""The React plan must use the same Top-N and allocation rules as Streamlit."""

from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import app_mode, simple_portfolio
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def test_plan_matches_legacy_selection_and_allocation_without_writing(tmp_path):
    seed_fixture(tmp_path)
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    original_stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
    with TestClient(app) as api:
        response = api.post("/api/v1/portfolio/plan", json={
            "n_positions": 5, "capital_eur": 1000, "holdings_text": "t000,80\nOUT,25",
            "new_capital_eur": 200,
        })
        assert response.status_code == 200, response.text
        plan = response.json()
        snapshot = app.state.market.repository.ranking(app_mode.FROZEN_WEIGHTS, TODAY)
        expected = simple_portfolio.target_portfolio(snapshot.table, 5)
        allocation = simple_portfolio.allocate_new_capital(expected, {"T000": 80, "OUT": 25}, 200)
        assert [row["symbol"] for row in plan["target"]] == expected.index.tolist()
        assert [row["weight_percent"] for row in plan["target"]] == expected["weight_pct"].tolist()
        assert plan["allocations"] == [
            {"symbol": item["symbol"], "name": item["name"], "amount_eur": item["amount"]}
            for item in allocation["allocations"]
        ]
        assert plan["outside_target"] == allocation["outside_target"]
        assert plan["status"] == "EXPERIMENTAL"
        assert plan["independent_advantage_demonstrated"] is False
        assert plan["target"][0]["amount_eur"] == 1000 / len(expected)
        assert api.post("/api/v1/portfolio/plan", json={}).json()["status"] == "FROZEN"
    assert (tmp_path / "gabi.db").stat().st_mtime_ns == original_stamp
    assert not (tmp_path / "gabi_jobs.db").exists()


def test_plan_rejects_invalid_holdings_before_market_read(tmp_path):
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as api:
        for holdings in ("AAPL,-1", "AAPL,nan", "AAPL,Infinity", "../../key,2"):
            response = api.post("/api/v1/portfolio/plan", json={"holdings_text": holdings})
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid_holdings"
    assert not (tmp_path / "gabi.db").exists()


def test_comparison_reuses_ranking_metrics_and_units(tmp_path):
    seed_fixture(tmp_path)
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as api:
        ranking = api.get("/api/v1/ranking?limit=50&hide_no_data=false").json()
        symbols = [ranking["items"][1]["symbol"], ranking["items"][0]["symbol"]]
        comparison = api.get("/api/v1/comparison", params=[("symbols", symbol) for symbol in symbols])
        assert comparison.status_code == 200, comparison.text
        body = comparison.json()
        assert [row["symbol"] for row in body["items"]] == symbols
        reference = {row["symbol"]: row for row in ranking["items"]}
        assert body["items"] == [reference[symbol] for symbol in symbols]
        assert body["revision"] == ranking["revision"]
        assert api.get("/api/v1/comparison", params=[("symbols", symbols[0])] * 2).status_code == 422
