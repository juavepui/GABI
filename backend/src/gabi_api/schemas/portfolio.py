"""Explicit units and provenance for the read-only portfolio plan."""

from datetime import date
from typing import Literal

from pydantic import Field

from gabi.application.portfolio.planning import PortfolioPlan
from gabi_api.schemas.market import DataResponse, WireModel, data_response, finite, text_or_none


class PlanRequest(WireModel):
    n_positions: int = Field(default=20, ge=5, le=30)
    capital_eur: float = Field(default=1000, ge=0, le=1e9, allow_inf_nan=False)
    holdings_text: str = Field(default="", max_length=5000)
    new_capital_eur: float = Field(default=1000, ge=0, le=1e9, allow_inf_nan=False)


class TargetPosition(WireModel):
    symbol: str
    name: str | None
    sector: str | None
    score_points: float | None
    score_coverage_fraction: float | None
    price_usd: float | None
    weight_percent: float
    amount_eur: float


class CapitalAllocation(WireModel):
    symbol: str
    name: str | None
    amount_eur: float


class PlanResponse(WireModel):
    target: list[TargetPosition]
    allocations: list[CapitalAllocation]
    remaining_eur: float
    outside_target: list[str]
    data: DataResponse
    generated_at: date
    revision: str
    n_positions: int
    model_id: str
    status: Literal["FROZEN", "EXPERIMENTAL"]
    evidence_note: str = "El Top-20 tiene evidencia retrospectiva; no hay ventaja independiente demostrada sobre SPY."
    independent_advantage_demonstrated: Literal[False] = False


def plan_response(plan: PortfolioPlan) -> PlanResponse:
    return PlanResponse(
        target=[TargetPosition(symbol=str(symbol), name=text_or_none(row.get("name")),
                               sector=text_or_none(row.get("sector")), score_points=finite(row.get("composite_score")),
                               score_coverage_fraction=finite(row.get("score_coverage")),
                               price_usd=finite(row.get("price")), weight_percent=float(row["weight_pct"]),
                               amount_eur=plan.capital_eur * float(row["weight_pct"]) / 100)
                for symbol, row in plan.target.iterrows()],
        allocations=[CapitalAllocation(symbol=item["symbol"], name=text_or_none(item["name"]),
                                       amount_eur=float(item["amount"])) for item in plan.allocations],
        remaining_eur=plan.remaining_eur, outside_target=plan.outside_target,
        data=data_response(plan.data), generated_at=plan.generated_at, revision=plan.revision,
        n_positions=plan.n_positions, model_id=plan.model_id, status=plan.status,
    )
