"""Only explicitly published research metadata is readable over HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from gabi.application.research.catalog import ResearchCatalog
from gabi_api.schemas.research import ResearchOverview, SearchTrials

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def service(request: Request) -> ResearchCatalog:
    return request.app.state.research_catalog


Catalog = Annotated[ResearchCatalog, Depends(service)]


@router.get("/overview", response_model=ResearchOverview)
def overview(catalog: Catalog) -> dict:
    return catalog.overview()


@router.get("/trials", response_model=SearchTrials)
def trials(catalog: Catalog, offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
           limit: Annotated[int, Query(ge=1, le=50)] = 25,
           family: Annotated[str | None, Query(max_length=80)] = None) -> dict:
    return catalog.trials(offset=offset, limit=limit, family=family)
