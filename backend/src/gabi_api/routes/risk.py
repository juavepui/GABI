from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from gabi.application.portfolio.risk import PortfolioRisk
from gabi_api.schemas.risk import (
    PolicyProposal,
    PortfolioPolicyInput,
    PortfolioPolicyRevision,
    PortfolioPolicyState,
    RiskPanel,
)

router = APIRouter(prefix="/api/v1/portfolio/risk", tags=["portfolio"])


def service(request: Request) -> PortfolioRisk:
    return request.app.state.portfolio_risk


@router.get("", response_model=RiskPanel)
def panel(risk: Annotated[PortfolioRisk, Depends(service)]) -> RiskPanel:
    """Read-only exposure of Mi cartera from the cache: it never downloads nor writes."""
    return RiskPanel.model_validate(risk.panel())


@router.get("/policy", response_model=PortfolioPolicyState)
def policy(risk: Annotated[PortfolioRisk, Depends(service)]) -> PortfolioPolicyState:
    return PortfolioPolicyState.model_validate(risk.policy_state())


@router.post("/policy", response_model=PortfolioPolicyRevision, status_code=201)
def save_policy(body: PortfolioPolicyInput,
                risk: Annotated[PortfolioRisk, Depends(service)]) -> PortfolioPolicyRevision:
    return PortfolioPolicyRevision.model_validate(risk.save_policy(body.model_dump()))


@router.get("/proposal", response_model=PolicyProposal)
def proposal(risk: Annotated[PortfolioRisk, Depends(service)],
             contribution_eur: Annotated[float, Query(ge=0, le=1e8)] = 700,
             n_positions: Annotated[int, Query(ge=5, le=30)] = 20) -> PolicyProposal:
    """Read-only: equal weight against the policy limits and the orders a contribution needs; nothing is sent."""
    return PolicyProposal.model_validate(risk.proposal(contribution_eur, n_positions))
