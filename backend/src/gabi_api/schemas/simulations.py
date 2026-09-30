from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from gabi_api.schemas.market import WireModel


class SimulationCreate(WireModel):
    name: str = Field(min_length=1, max_length=80)
    initial_cash: float = Field(gt=0, le=1e9, allow_inf_nan=False)
    stock_commission: float = Field(default=1, ge=0, le=1e9, allow_inf_nan=False)
    etf_commission: float = Field(default=0, ge=0, le=1e9, allow_inf_nan=False)
    spread_bps: float = Field(default=10, ge=0, le=1e9, allow_inf_nan=False)
    base_currency: Literal["USD", "EUR"] = "USD"


class SimulationPortfolio(SimulationCreate):
    id: int
    created_at: datetime
    status: Literal["EXPERIMENTAL"] = "EXPERIMENTAL"


class SimulationList(WireModel):
    items: list[SimulationPortfolio]


class SimulationTradeCreate(WireModel):
    symbol: str = Field(min_length=1, max_length=20)
    asset_type: Literal["STOCK", "ETF"]
    side: Literal["BUY", "SELL"]
    requested_date: date
    notional: float = Field(gt=0, le=1e9, allow_inf_nan=False)
    market: Literal["XNYS", "XETR", "XLON", "XMAD", "XPAR"] = "XNYS"
    quote_currency: Literal["USD", "EUR", "GBP"] = "USD"
    commission: float | None = Field(default=None, ge=0, le=1e9, allow_inf_nan=False)
    spread_bps: float | None = Field(default=None, ge=0, le=1e9, allow_inf_nan=False)
    fx_rate: float | None = Field(default=None, gt=0, le=1e9, allow_inf_nan=False)
    fx_fee_bps: float = Field(default=0, ge=0, le=1e9, allow_inf_nan=False)


class SimulationTrade(SimulationTradeCreate):
    id: int
    portfolio_id: int
    execution_date: date
    reference_close: float
    commission: float
    spread_bps: float
    fx_rate: float
    created_at: datetime


class SimulationTrades(WireModel):
    items: list[SimulationTrade]


class CurvePoint(WireModel):
    date: date
    value: float | None
    cash: float


class SimulationResult(WireModel):
    summary: dict[str, Any]
    curve: list[CurvePoint]
    positions: dict[str, float]
    cash: float
    status: Literal["EXPERIMENTAL"] = "EXPERIMENTAL"
    note: str = "Simulación retrospectiva local; no acredita ventaja independiente ni envía órdenes."


class UndoResult(WireModel):
    undone: bool
