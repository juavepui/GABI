from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from gabi.application.portfolio.benchmark import InvestorBenchmark
from gabi_api.schemas.investor import (
    HoldingsBenchmarkResult,
    InvestorBenchmarkResult,
    InvestorProfileInput,
    InvestorProfileRevision,
    InvestorProfileState,
)

router = APIRouter(prefix="/api/v1/portfolio/investor", tags=["portfolio"])


def service(request: Request) -> InvestorBenchmark:
    return request.app.state.investor


@router.get("/profile", response_model=InvestorProfileState)
def profile(investor: Annotated[InvestorBenchmark, Depends(service)]) -> InvestorProfileState:
    """Read-only: the current profile and its earlier revisions; it never initializes the table."""
    return InvestorProfileState.model_validate({"current": investor.profile(), "revisions": investor.revisions()})


@router.post("/profile", response_model=InvestorProfileRevision, status_code=201)
def save(body: InvestorProfileInput,
         investor: Annotated[InvestorBenchmark, Depends(service)]) -> InvestorProfileRevision:
    return InvestorProfileRevision.model_validate(investor.save(body.model_dump()))


@router.get("/benchmark", response_model=InvestorBenchmarkResult)
def benchmark(investor: Annotated[InvestorBenchmark, Depends(service)],
              start: Annotated[date | None, Query()] = None) -> InvestorBenchmarkResult:
    """Read-only from cached prices: the profile's contributions bought in SPY; it never downloads."""
    return InvestorBenchmarkResult.model_validate(investor.benchmark(start))


@router.get("/holdings-benchmark", response_model=HoldingsBenchmarkResult)
def holdings_benchmark(investor: Annotated[InvestorBenchmark, Depends(service)]) -> HoldingsBenchmarkResult:
    """Read-only from cached prices: the real purchases against SPY bought with the same euros."""
    return HoldingsBenchmarkResult.model_validate(investor.holdings())
