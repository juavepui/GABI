from typing import Annotated

from fastapi import APIRouter, Depends, Request

from gabi.application.market.macro import MacroQueries
from gabi.application.market.market_health import MarketHealthQueries
from gabi_api.schemas.macro import MacroLabel, MacroPoint, MacroResponse, MarketHealthResponse

router = APIRouter(prefix="/api/v1/market", tags=["market"])


def service(request: Request) -> MacroQueries:
    return request.app.state.macro


@router.get("/macro", response_model=MacroResponse)
def snapshot(queries: Annotated[MacroQueries, Depends(service)]) -> MacroResponse:
    rows = queries.snapshot()
    return MacroResponse(items=[MacroPoint.model_validate(row) for row in rows],
                         labels=[MacroLabel.model_validate(label) for label in queries.labels(rows)],
                         fred_key_configured=queries.key_configured())


def market_health(request: Request) -> MarketHealthQueries:
    return request.app.state.market_health


@router.get("/health", response_model=MarketHealthResponse)
def health(queries: Annotated[MarketHealthQueries, Depends(market_health)]) -> dict:
    """Read-only traffic light of the market (#308): context, never a signal; nothing is downloaded."""
    return queries.current()
