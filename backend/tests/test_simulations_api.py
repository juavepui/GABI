from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import config, sim_portfolios
from gabi.application.administration.jobs import JobCommand
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def test_simulations_share_legacy_tables_costs_and_replay(tmp_path, monkeypatch):
    seed_fixture(tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as api:
        assert api.get("/api/v1/portfolio/simulations").json()["items"] == []
        created = api.post("/api/v1/portfolio/simulations", json={
            "name": "Plan local", "initial_cash": 10000, "stock_commission": 1,
            "spread_bps": 10, "base_currency": "USD",
        })
        assert created.status_code == 201, created.text
        portfolio_id = created.json()["id"]
        assert int(sim_portfolios.list_portfolios().iloc[0]["id"]) == portfolio_id
        trade = api.post(f"/api/v1/portfolio/simulations/{portfolio_id}/trades", json={
            "symbol": "T000", "asset_type": "STOCK", "side": "BUY",
            "requested_date": "2026-09-28", "notional": 1000,
        })
        assert trade.status_code == 201, trade.text
        assert trade.json()["commission"] == 1
        assert len(sim_portfolios.list_trades(portfolio_id)) == 1
        result = api.get(f"/api/v1/portfolio/simulations/{portfolio_id}/result")
        assert result.status_code == 200, result.text
        expected = sim_portfolios.summarize(sim_portfolios.portfolio_history(portfolio_id))
        assert result.json()["summary"]["return"] == expected["return"]
        assert result.json()["summary"]["benchmark_return"] == expected["benchmark_return"]
        assert result.json()["status"] == "EXPERIMENTAL"
        comparison = LegacyExecutor(Settings(tmp_path))(JobCommand("sim_compare"))
        assert comparison["items"][0]["id"] == portfolio_id
        assert comparison["items"][0]["return"] == expected["return"]
        assert comparison["items"][0]["benchmark_return"] == expected["benchmark_return"]
        assert api.post(f"/api/v1/portfolio/simulations/{portfolio_id}/undo").json()["undone"] is True
        assert sim_portfolios.list_trades(portfolio_id).empty


def test_simulations_get_is_inert_and_rejects_uncached_trade(tmp_path):
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as api:
        assert api.get("/api/v1/portfolio/simulations").json()["items"] == []
        created = api.post("/api/v1/portfolio/simulations", json={"name": "Vacía", "initial_cash": 1000})
        assert created.status_code == 201
        portfolio_id = created.json()["id"]
        trade = api.post(f"/api/v1/portfolio/simulations/{portfolio_id}/trades", json={
            "symbol": "AAPL", "asset_type": "STOCK", "side": "BUY",
            "requested_date": "2026-09-28", "notional": 100,
        })
        assert trade.status_code == 422
        assert api.get(f"/api/v1/portfolio/simulations/{portfolio_id}/trades").json()["items"] == []
