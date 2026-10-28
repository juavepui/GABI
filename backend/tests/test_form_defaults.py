"""Form defaults (#190) come from the backend and are valid requests of the forms they fill."""

from fastapi.testclient import TestClient

from gabi.domain.portfolio import broker_costs
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app
from gabi_api.schemas.decisions import DecisionPolicy
from gabi_api.schemas.jobs import BacktestOptions, PortfolioLabOptions
from gabi_api.schemas.simulations import SimulationCreate, SimulationTradeCreate


def test_the_defaults_are_the_request_schemas_own_and_valid_requests(tmp_path):
    with TestClient(create_app(Settings(tmp_path))) as api:
        response = api.get("/api/v1/forms/defaults")
        assert response.status_code == 200, response.text
        body = response.json()
    assert not tmp_path.joinpath("gabi.db").exists()  # Constant values: nothing is read or created.
    assert body["decision_policy"] == DecisionPolicy().model_dump()
    simulation, trade = body["simulation"], body["simulation_trade"]
    SimulationCreate.model_validate(simulation | {"name": "Prueba"})
    assert simulation["spread_bps"] == SimulationCreate.model_fields["spread_bps"].default
    SimulationTradeCreate.model_validate(trade | {"symbol": "AAPL", "requested_date": "2026-01-02", "notional": 100})
    backtest = body["backtest"]
    assert backtest["commission_usd"] == broker_costs.STOCK_FEE_USD
    for top_n in (backtest["top_n_v1"], backtest["top_n_v2"]):
        BacktestOptions.model_validate({key: backtest[key] for key in BacktestOptions.model_fields if key in backtest}
                                       | {"top_n": top_n})
    lab = body["portfolio_lab"]
    PortfolioLabOptions.model_validate({key: lab[key] for key in PortfolioLabOptions.model_fields})
    assert backtest["start"] < backtest["end"] and lab["start"] < lab["end"]
