"""Only explicitly published research metadata is readable over HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response

from gabi.application.administration.jobs import Jobs
from gabi.application.errors import QueryError
from gabi.application.research.backtest_diagnostics import BacktestDiagnostics
from gabi.application.research.backtests import backtest_preview
from gabi.application.research.blind import BlindValidationQueries
from gabi.application.research.catalog import ResearchCatalog
from gabi.application.research.estimates import EstimateQueries
from gabi.application.research.experiment_statistics import ExperimentStatistics
from gabi.application.research.experiments import ExperimentQueries
from gabi.application.research.factors import quantile_means
from gabi.application.research.historical_queries import HistoricalQueries
from gabi.application.research.published_factors import PublishedFactorQueries
from gabi_api.schemas.research import (
    BacktestDiagnosticsResponse,
    BacktestFactorsPreview,
    BacktestPreview,
    BlindStatuses,
    DeflatedSharpe,
    EstimateAnalysisPreview,
    EstimateCaptureStatus,
    ExperimentDetail,
    ExperimentList,
    ExperimentTailRisk,
    FactorPreview,
    HistoricalOutcomes,
    HistoricalPreview,
    HistoricalTable,
    PreparationResult,
    PublishedFactors,
    ResearchOverview,
    SearchTrials,
)

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def service(request: Request) -> ResearchCatalog:
    return request.app.state.research_catalog


Catalog = Annotated[ResearchCatalog, Depends(service)]


def jobs(request: Request) -> Jobs:
    return request.app.state.jobs


Queue = Annotated[Jobs, Depends(jobs)]


def diagnostics_service(request: Request) -> BacktestDiagnostics:
    return request.app.state.backtest_diagnostics


Diagnostics = Annotated[BacktestDiagnostics, Depends(diagnostics_service)]


def historical_service(request: Request) -> HistoricalQueries:
    return request.app.state.historical_queries


HistoricalRanking = Annotated[HistoricalQueries, Depends(historical_service)]


def blind_service(request: Request) -> BlindValidationQueries:
    return request.app.state.blind_validations


Blind = Annotated[BlindValidationQueries, Depends(blind_service)]


def published_factor_service(request: Request) -> PublishedFactorQueries:
    return request.app.state.published_factors


Published = Annotated[PublishedFactorQueries, Depends(published_factor_service)]


def estimate_service(request: Request) -> EstimateQueries:
    return request.app.state.estimate_queries


Estimates = Annotated[EstimateQueries, Depends(estimate_service)]


def experiment_service(request: Request) -> ExperimentQueries:
    return request.app.state.experiments


Experiments = Annotated[ExperimentQueries, Depends(experiment_service)]


@router.get("/experiments", response_model=ExperimentList)
def experiments(query: Experiments, family: Annotated[str | None, Query(max_length=200)] = None,
                stage: Annotated[str | None, Query(max_length=20)] = None,
                offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
                limit: Annotated[int, Query(ge=1, le=200)] = 50) -> dict:
    return query.list(family, stage, offset, limit)


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetail)
def experiment(experiment_id: Annotated[int, Path(ge=1)], query: Experiments) -> dict:
    return query.detail(experiment_id)


def statistics_service(request: Request) -> ExperimentStatistics:
    return request.app.state.experiment_statistics


Statistics = Annotated[ExperimentStatistics, Depends(statistics_service)]


@router.get("/experiments/{experiment_id}/tail-risk", response_model=ExperimentTailRisk)
def experiment_tail_risk(experiment_id: Annotated[int, Path(ge=1)], query: Statistics) -> dict:
    return query.tail_risk(experiment_id)


@router.get("/experiment-statistics/deflated-sharpe", response_model=DeflatedSharpe)
def deflated_sharpe(query: Statistics, experiment_id: Annotated[int, Query(ge=1)],
                    family: Annotated[str | None, Query(max_length=200)] = None) -> dict:
    return query.deflated_sharpe(experiment_id, family)


@router.get("/blind-validations", response_model=BlindStatuses)
def blind_validations(query: Blind) -> dict:
    return query.list_status()


@router.get("/estimate-captures", response_model=EstimateCaptureStatus)
def estimate_captures(query: Estimates) -> dict:
    return query.status()


@router.get("/estimate-analysis/{job_id}", response_model=EstimateAnalysisPreview)
def estimate_analysis_preview(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], queue: Queue) -> dict:
    job = queue.get(job_id)
    if job["kind"] != "estimate_analysis":
        raise QueryError("job_not_found", "El análisis de estimaciones no existe.", 404)
    result = queue.result(job_id)
    return {"job_id": job_id, "status": result["status"], "observed_cutoff": result["observed_cutoff"],
            "period": result["period"], "horizons_months": result["horizons_months"],
            "batches_available": result["batches_available"], "batches_needed": result["batches_needed"],
            "span_days": result["span_days"], "span_days_needed": result["span_days_needed"],
            "reason": result["reason"], "summary": result["summary"],
            "independent_advantage_demonstrated": result["independent_advantage_demonstrated"],
            "result_sha256": job["result_sha256"]}


@router.get("/overview", response_model=ResearchOverview)
def overview(catalog: Catalog) -> dict:
    return catalog.overview()


@router.get("/published-factors", response_model=PublishedFactors)
def published_factors(query: Published) -> dict:
    return query.overview()


@router.get("/published-factors/exports/{name}")
def published_factor_export(name: str, query: Published) -> Response:
    contents = query.export(name)
    return Response(contents, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/trials", response_model=SearchTrials)
def trials(catalog: Catalog, offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
           limit: Annotated[int, Query(ge=1, le=50)] = 25,
           family: Annotated[str | None, Query(max_length=80)] = None) -> dict:
    return catalog.trials(offset=offset, limit=limit, family=family)


@router.get("/historical/{job_id}", response_model=HistoricalPreview)
def historical_preview(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], query: HistoricalRanking,
                       coverage_threshold: Annotated[float, Query(ge=0, le=1)] = 0.7) -> dict:
    return query.preview(job_id, coverage_threshold)


@router.get("/historical/{job_id}/table", response_model=HistoricalTable)
def historical_table(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], query: HistoricalRanking,
                     hide_no_data: bool = True, sort: Annotated[str | None, Query(max_length=60)] = None,
                     descending: bool = True, offset: Annotated[int, Query(ge=0)] = 0,
                     limit: Annotated[int, Query(ge=1, le=200)] = 100) -> dict:
    return query.table(job_id, hide_no_data=hide_no_data, sort=sort, descending=descending,
                       offset=offset, limit=limit)


@router.get("/historical-outcomes/{job_id}", response_model=HistoricalOutcomes)
def historical_outcomes(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], queue: Queue) -> dict:
    job = queue.get(job_id)
    if job["kind"] != "historical_outcomes":
        raise QueryError("job_not_found", "La evaluación posterior no existe.", 404)
    return queue.result(job_id) | {"job_id": job_id, "result_sha256": job["result_sha256"]}


@router.get("/backtests/{job_id}", response_model=BacktestPreview)
def backtest_result(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], queue: Queue) -> dict:
    job = queue.get(job_id)
    if job["kind"] not in {"backtest_v1", "backtest_v2"}:
        raise QueryError("job_not_found", "El backtest no existe.", 404)
    return backtest_preview(queue.result(job_id)) | {"job_id": job_id, "result_sha256": job["result_sha256"]}


@router.get("/backtests/{job_id}/diagnostics", response_model=BacktestDiagnosticsResponse)
def backtest_diagnostics(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], query: Diagnostics,
                         tax_capital: Annotated[float, Query(ge=1_000, le=100_000_000)] = 100_000.0,
                         coverage_threshold: Annotated[float, Query(ge=0, le=1)] = 0.7) -> dict:
    return query.diagnostics(job_id, tax_capital, coverage_threshold)


@router.get("/backtest-factors/{job_id}", response_model=BacktestFactorsPreview)
def backtest_factors(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], queue: Queue) -> dict:
    job = queue.get(job_id)
    if job["kind"] != "backtest_factors":
        raise QueryError("job_not_found", "El contraste Fama-French no existe.", 404)
    return queue.result(job_id) | {"job_id": job_id, "result_sha256": job["result_sha256"]}


@router.get("/preparations/{job_id}", response_model=PreparationResult)
def preparation(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], queue: Queue) -> dict:
    job = queue.get(job_id)
    if job["kind"] != "prepare_history":
        raise QueryError("job_not_found", "La preparación de datos no existe.", 404)
    result = queue.result(job_id)
    return result | {"job_id": job_id, "scope": result["options"]["scope"]}


@router.get("/factors/{job_id}", response_model=FactorPreview)
def factor_preview(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], queue: Queue) -> dict:
    job = queue.get(job_id)
    if job["kind"] != "factor_analysis":
        raise QueryError("job_not_found", "El análisis de factores no existe.", 404)
    result = queue.result(job_id)
    return {
        "job_id": job_id, "start": result["start"], "end": result["end"],
        "months": result["months"], "mode": result["mode"],
        "max_symbols": result["max_symbols"], "status": result["status"],
        "independent_advantage_demonstrated": result["independent_advantage_demonstrated"],
        "summary": result["summary"], "turnover": result["turnover"],
        "quantile_means": quantile_means(result["quantile_returns"]),
        "skipped": result["skipped"], "skipped_count": len(result["skipped"]),
        "result_sha256": job["result_sha256"],
    }
