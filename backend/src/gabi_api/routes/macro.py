from typing import Annotated

from fastapi import APIRouter, Depends, Request

from gabi.application.market.macro import MacroQueries
from gabi_api.schemas.macro import MacroPoint, MacroResponse

router = APIRouter(prefix="/api/v1/market", tags=["market"])


def service(request: Request) -> MacroQueries:
    return request.app.state.macro


@router.get("/macro", response_model=MacroResponse)
def snapshot(queries: Annotated[MacroQueries, Depends(service)]) -> MacroResponse:
    return MacroResponse(items=[MacroPoint.model_validate(row) for row in queries.snapshot()])
