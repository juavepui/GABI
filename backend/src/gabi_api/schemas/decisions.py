"""Explicit experimental decision contracts; percentages are of total wealth."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from gabi_api.schemas.market import WireModel


class DecisionPolicy(WireModel):
    min_score: float = Field(default=65, ge=0, le=100, allow_inf_nan=False)
    min_coverage: float = Field(default=0.70, ge=0, le=1, allow_inf_nan=False)
    max_positions: int = Field(default=10, ge=1, le=30)
    max_position_pct: float = Field(default=5, gt=0, le=100, allow_inf_nan=False)
    max_sector_pct: float = Field(default=20, gt=0, le=100, allow_inf_nan=False)
    max_invested_pct: float = Field(default=50, gt=0, le=100, allow_inf_nan=False)
    max_volatility: float = Field(default=0.60, gt=0, le=10, allow_inf_nan=False)
    min_drawdown: float = Field(default=-0.50, ge=-1, le=0, allow_inf_nan=False)
    max_price_age_days: int = Field(default=7, ge=1, le=30)
    trade_threshold_pct: float = Field(default=0.50, ge=0, le=100, allow_inf_nan=False)
    constrained_optimizer: bool = False
    turnover_penalty: float = Field(default=0, ge=0, le=0.20, allow_inf_nan=False)


class DecisionJobSave(WireModel):
    job_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=80)


class DecisionRename(WireModel):
    name: str = Field(min_length=1, max_length=80)


class DecisionSummary(WireModel):
    id: int
    name: str
    created_at: datetime
    method: str


class DecisionList(WireModel):
    items: list[DecisionSummary]


class SavedDecision(DecisionSummary):
    decisions: list[dict[str, Any]]
    policy: dict[str, Any]
    holdings: dict[str, float]
    status: Literal["EXPERIMENTAL"] = "EXPERIMENTAL"


class DeleteDecision(WireModel):
    deleted: bool


class DecisionProgress(WireModel):
    as_of_date: str
    created_at: datetime
    today: str
    data_as_of: str | None
    stale: bool
    detail: list[dict[str, Any]]
    available: int
    requested: int
    portfolio_return: float | None
    benchmark_return: float | None
    excess_return: float | None
    missing: list[str]
    curve: list[dict[str, Any]]
