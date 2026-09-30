from typing import Annotated

from fastapi import APIRouter, Depends, Request

from gabi.application.portfolio.planning import PortfolioQueries
from gabi_api.schemas.portfolio import PlanRequest, PlanResponse, plan_response

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


def service(request: Request) -> PortfolioQueries:
    return request.app.state.portfolio


@router.post("/plan", response_model=PlanResponse)
def plan(body: PlanRequest, queries: Annotated[PortfolioQueries, Depends(service)]) -> PlanResponse:
    return plan_response(queries.plan(body.n_positions, body.capital_eur, body.holdings_text, body.new_capital_eur))
