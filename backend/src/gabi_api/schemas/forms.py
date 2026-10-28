"""Default values of the forms (#190): the backend owns them; React only fills the fields.

Decision and simulation defaults are the request schemas' own defaults, read from them so they cannot drift.
Backtest and Portfolio Lab requests have no defaults of their own (every option is explicit in a job), so
their starting values live here, next to the request schemas they fill.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gabi.domain.portfolio import broker_costs
from gabi_api.schemas.decisions import DecisionPolicy
from gabi_api.schemas.simulations import SimulationCreate, SimulationTradeCreate

Scheme = Literal["equal_weight", "inverse_vol", "min_variance", "score_weighted", "score_constrained", "risk_parity"]
SCHEMES: tuple[Scheme, ...] = ("equal_weight", "inverse_vol", "min_variance", "score_weighted", "score_constrained",
                               "risk_parity")


def _default(model: type[BaseModel], name: str):
    return model.model_fields[name].default


class Defaults(BaseModel):
    # Every value is present in the response: the contract marks them required, not optional.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class DecisionPolicyDefaults(DecisionPolicy):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class SimulationDefaults(Defaults):
    initial_cash: float = 10_000
    base_currency: Literal["USD", "EUR"] = _default(SimulationCreate, "base_currency")
    stock_commission: float = _default(SimulationCreate, "stock_commission")
    etf_commission: float = _default(SimulationCreate, "etf_commission")
    spread_bps: float = _default(SimulationCreate, "spread_bps")


class SimulationTradeDefaults(Defaults):
    asset_type: Literal["STOCK", "ETF"] = _default(SimulationTradeCreate, "asset_type")
    side: Literal["BUY", "SELL"] = _default(SimulationTradeCreate, "side")
    # None: inferred from the ticker's suffix (#192).
    market: Literal["XNYS", "XETR", "XLON", "XMAD", "XPAR"] | None = _default(SimulationTradeCreate, "market")
    quote_currency: Literal["USD", "EUR", "GBP"] | None = _default(SimulationTradeCreate, "quote_currency")
    fx_fee_bps: float = _default(SimulationTradeCreate, "fx_fee_bps")


class BacktestDefaults(Defaults):
    start: str = "2019-01-02"
    end: str = "2020-01-02"
    months: Literal[1, 3, 6, 12] = 3
    top_n_v1: int = 10  # The classic engine compares 10 companies; V2, a 20-position portfolio.
    top_n_v2: int = 20
    rotation_hurdle_points: float = 0
    cost_bps: float = 10
    universe_size: Literal[50, 100, 500] = 50
    mode: Literal["validation", "fast_dev"] = "fast_dev"
    max_symbols: Literal[50, 100, 200] = 200
    initial_capital: float = 100_000
    commission_usd: float = broker_costs.STOCK_FEE_USD
    spread_bps: float = 10


class PortfolioLabDefaults(Defaults):
    start: str = "2019-01-02"
    end: str = "2024-01-02"
    months: Literal[1, 3, 6, 12] = 3
    top_n: int = 20
    initial_capital: float = 100_000
    schemes: list[Scheme] = Field(default_factory=lambda: list(SCHEMES))
    mode: Literal["validation", "fast_dev"] = "fast_dev"
    max_symbols: Literal[50, 100, 200] = 100


class FormDefaults(Defaults):
    decision_policy: DecisionPolicyDefaults = Field(default_factory=DecisionPolicyDefaults)
    simulation: SimulationDefaults = Field(default_factory=SimulationDefaults)
    simulation_trade: SimulationTradeDefaults = Field(default_factory=SimulationTradeDefaults)
    backtest: BacktestDefaults = Field(default_factory=BacktestDefaults)
    portfolio_lab: PortfolioLabDefaults = Field(default_factory=PortfolioLabDefaults)
