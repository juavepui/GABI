from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from gabi.application.portfolio.holdings import Holdings
from gabi_api.schemas.holdings import (
    Holding,
    HoldingCreate,
    HoldingDeleted,
    HoldingImport,
    HoldingImportResult,
    HoldingList,
    HoldingsSummary,
    sector_weights,
)

router = APIRouter(prefix="/api/v1/portfolio/holdings", tags=["portfolio"])


def service(request: Request) -> Holdings:
    return request.app.state.holdings


@router.get("", response_model=HoldingsSummary)
def summary(holdings: Annotated[Holdings, Depends(service)]) -> HoldingsSummary:
    """Read-only valuation from cached prices: it never downloads nor initializes the table."""
    result = holdings.summary()
    return HoldingsSummary.model_validate(result | {"sectors": sector_weights(result["sectors"])})


@router.get("/lots", response_model=HoldingList)
def lots(holdings: Annotated[Holdings, Depends(service)]) -> HoldingList:
    return HoldingList(items=[Holding.model_validate(row) for row in holdings.lots()])


@router.post("", response_model=Holding, status_code=201)
def add(body: HoldingCreate, holdings: Annotated[Holdings, Depends(service)]) -> Holding:
    return Holding.model_validate(holdings.add(body.model_dump()))


@router.post("/import", response_model=HoldingImportResult, status_code=201)
def import_csv(body: HoldingImport, holdings: Annotated[Holdings, Depends(service)]) -> HoldingImportResult:
    return HoldingImportResult.model_validate(holdings.import_csv(body.csv))


@router.post("/{lot_id}", response_model=Holding)
def update(lot_id: Annotated[int, Path(ge=1)], body: HoldingCreate,
           holdings: Annotated[Holdings, Depends(service)]) -> Holding:
    return Holding.model_validate(holdings.update(lot_id, body.model_dump()))


@router.post("/{lot_id}/delete", response_model=HoldingDeleted)
def delete(lot_id: Annotated[int, Path(ge=1)],
           holdings: Annotated[Holdings, Depends(service)]) -> HoldingDeleted:
    return HoldingDeleted(deleted=holdings.delete(lot_id))
