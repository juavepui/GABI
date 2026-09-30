"""Only explicitly published research metadata is readable over HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from gabi.application.administration.jobs import Jobs
from gabi.application.errors import QueryError
from gabi.application.research.blind import BlindValidationQueries
from gabi.application.research.catalog import ResearchCatalog
from gabi_api.schemas.research import BlindStatuses, HistoricalPreview, ResearchOverview, SearchTrials

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def service(request: Request) -> ResearchCatalog:
    return request.app.state.research_catalog


Catalog = Annotated[ResearchCatalog, Depends(service)]


def jobs(request: Request) -> Jobs:
    return request.app.state.jobs


Queue = Annotated[Jobs, Depends(jobs)]


def blind_service(request: Request) -> BlindValidationQueries:
    return request.app.state.blind_validations


Blind = Annotated[BlindValidationQueries, Depends(blind_service)]


@router.get("/blind-validations", response_model=BlindStatuses)
def blind_validations(query: Blind) -> dict:
    return query.list_status()


@router.get("/overview", response_model=ResearchOverview)
def overview(catalog: Catalog) -> dict:
    return catalog.overview()


@router.get("/trials", response_model=SearchTrials)
def trials(catalog: Catalog, offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
           limit: Annotated[int, Query(ge=1, le=50)] = 25,
           family: Annotated[str | None, Query(max_length=80)] = None) -> dict:
    return catalog.trials(offset=offset, limit=limit, family=family)


@router.get("/historical/{job_id}", response_model=HistoricalPreview)
def historical_preview(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], queue: Queue) -> dict:
    job = queue.get(job_id)
    if job["kind"] != "historical_ranking":
        raise QueryError("job_not_found", "El ranking histórico no existe.", 404)
    result = queue.result(job_id)
    rows = result["rows"][:100]
    return {
        "job_id": job_id,
        "as_of": result["as_of"],
        "status": result["status"],
        "independent_advantage_demonstrated": result["independent_advantage_demonstrated"],
        "universe_info": result["universe_info"],
        "total": result["total"],
        "shown": len(rows),
        "rows": rows,
        "result_sha256": job["result_sha256"],
    }
