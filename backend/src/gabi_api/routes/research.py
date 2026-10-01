"""Only explicitly published research metadata is readable over HTTP."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response

from gabi.application.administration.jobs import Jobs
from gabi.application.errors import QueryError
from gabi.application.research.backtest_diagnostics import BacktestDiagnostics
from gabi.application.research.backtests import backtest_preview
from gabi.application.research.blind import BlindValidationQueries
from gabi.application.research.block_bootstrap_view import present
from gabi.application.research.catalog import ResearchCatalog
from gabi.application.research.estimates import EstimateQueries
from gabi.application.research.experiment_analysis import distribution_frame
from gabi.application.research.experiment_commands import ExperimentCommands
from gabi.application.research.experiment_statistics import ExperimentStatistics
from gabi.application.research.experiments import ExperimentQueries
from gabi.application.research.factors import quantile_means
from gabi.application.research.historical_queries import HistoricalQueries
from gabi.application.research.live_ledger import LiveLedgerCommands, LiveLedgerQueries
from gabi.application.research.published_factors import PublishedFactorQueries
from gabi.application.research.saved_audits import SavedAuditQueries
from gabi.domain.research.live_ledger import canonical
from gabi_api.schemas.research import (
    BacktestDiagnosticsResponse,
    BacktestFactorsPreview,
    BacktestPreview,
    BlindStatuses,
    DeflatedSharpe,
    DeletedExperiment,
    EstimateAnalysisPreview,
    EstimateCaptureStatus,
    ExperimentBootstrapPreview,
    ExperimentDetail,
    ExperimentList,
    ExperimentPboPreview,
    ExperimentTailRisk,
    FactorBenchmark,
    FactorPreview,
    FactorStability,
    HistoricalOutcomes,
    HistoricalPreview,
    HistoricalTable,
    LiveForwardReport,
    LiveLedgerDecision,
    LiveLedgerOverview,
    ManualExperimentRequest,
    PreparationResult,
    PublishedFactors,
    ResearchOverview,
    SavedAuditsOverview,
    SavedBlockBootstrap,
    SavedEvaluation,
    SavedOverfittingAudit,
    SavedRankStability,
    SaveEvaluationRequest,
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


def command_service(request: Request) -> ExperimentCommands:
    return request.app.state.experiment_commands


Commands = Annotated[ExperimentCommands, Depends(command_service)]


@router.post("/experiments", response_model=ExperimentDetail, status_code=201)
def create_experiment(body: ManualExperimentRequest, commands: Commands, query: Experiments) -> dict:
    return query.detail(commands.create(body.model_dump()))


@router.post("/experiments/{experiment_id}/delete", response_model=DeletedExperiment)
def delete_experiment(experiment_id: Annotated[int, Path(ge=1)], commands: Commands) -> dict:
    return commands.delete(experiment_id)


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


def _experiment_job(queue: Jobs, job_id: str, kind: str, missing: str) -> tuple[dict, dict]:
    job = queue.get(job_id)
    if job["kind"] != kind:
        raise QueryError("job_not_found", missing, 404)
    return job, queue.result(job_id)


@router.get("/experiment-pbo/{job_id}", response_model=ExperimentPboPreview)
def experiment_pbo(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], queue: Queue) -> dict:
    job, result = _experiment_job(queue, job_id, "experiment_pbo", "El cálculo PBO no existe.")
    return result | {"job_id": job_id, "result_sha256": job["result_sha256"]}


@router.get("/experiment-bootstrap/{job_id}", response_model=ExperimentBootstrapPreview)
def experiment_bootstrap(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], queue: Queue) -> dict:
    job, result = _experiment_job(queue, job_id, "experiment_bootstrap", "El bootstrap no existe.")
    view = (present(result["audit"], distribution_frame(result["distribution"]), result["block_order"])
            if result["audit"] is not None else None)
    return {key: result[key] for key in ("status", "independent_advantage_demonstrated", "experiments", "message")
            } | {"job_id": job_id, "result_sha256": job["result_sha256"], "view": view}


@router.get("/experiment-bootstrap/{job_id}/distributions.csv")
def experiment_bootstrap_distributions(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")],
                                       queue: Queue) -> Response:
    _, result = _experiment_job(queue, job_id, "experiment_bootstrap", "El bootstrap no existe.")
    if result["distribution"] is None:
        raise QueryError("result_unavailable", "Este bootstrap no tiene réplicas.", 404)
    return Response(distribution_frame(result["distribution"]).to_csv(index=False), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="block-bootstrap-distributions.csv"'})


def saved_audit_service(request: Request) -> SavedAuditQueries:
    return request.app.state.saved_audits


Saved = Annotated[SavedAuditQueries, Depends(saved_audit_service)]
MEDIA = {".csv": "text/csv; charset=utf-8", ".json": "application/json"}


@router.get("/saved-audits", response_model=SavedAuditsOverview)
def saved_audits(query: Saved) -> dict:
    return {name.replace("-", "_"): value for name, value in query.overview().items()}


@router.get("/saved-audits/overfitting", response_model=SavedOverfittingAudit)
def saved_overfitting(query: Saved) -> dict:
    return query.overfitting()


@router.get("/saved-audits/factor-benchmark", response_model=FactorBenchmark)
def saved_factor_benchmark(query: Saved) -> dict:
    return query.factor_benchmark()


@router.get("/saved-audits/factor-stability", response_model=FactorStability)
def saved_factor_stability(query: Saved) -> dict:
    return query.factor_stability()


@router.get("/saved-audits/block-bootstrap", response_model=SavedBlockBootstrap)
def saved_block_bootstrap(query: Saved, dataset: Annotated[str | None, Query(max_length=40)] = None) -> dict:
    return query.block_bootstrap(dataset)


@router.get("/saved-audits/rank-stability", response_model=SavedRankStability)
def saved_rank_stability(query: Saved, date: Annotated[str | None, Query(max_length=10)] = None) -> dict:
    return query.rank_stability(date)


@router.get("/saved-audits/{audit}/files/{filename}")
def saved_audit_file(audit: Annotated[str, Path(max_length=40)], filename: Annotated[str, Path(max_length=60)],
                     query: Saved) -> Response:
    contents = query.download(audit, filename)
    return Response(contents, media_type=MEDIA.get(filename[filename.rfind("."):], "application/octet-stream"),
                    headers={"Content-Disposition": f'attachment; filename="gabi-{audit}-{filename}"'})


def ledger_service(request: Request) -> LiveLedgerQueries:
    return request.app.state.live_ledger


def ledger_commands(request: Request) -> LiveLedgerCommands:
    return request.app.state.live_ledger_commands


Ledger = Annotated[LiveLedgerQueries, Depends(ledger_service)]
LedgerCommands = Annotated[LiveLedgerCommands, Depends(ledger_commands)]


@router.get("/live-ledger", response_model=LiveLedgerOverview)
def live_ledger(query: Ledger) -> dict:
    return query.overview()


@router.get("/live-ledger/decisions/{seq}", response_model=LiveLedgerDecision)
def live_ledger_decision(seq: Annotated[int, Path(ge=1)], query: Ledger) -> dict:
    return query.decision(seq)


@router.get("/live-ledger/decisions/{seq}/event.json")
def live_ledger_event(seq: Annotated[int, Path(ge=1)], query: Ledger) -> Response:
    return Response(canonical(query.event(seq)), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="gabi-live-ledger-{seq}.json"'})


@router.post("/live-ledger/evaluations", response_model=SavedEvaluation, status_code=201)
def save_live_evaluation(body: SaveEvaluationRequest, commands: LedgerCommands) -> dict:
    return commands.save_evaluation(body.job_id)


@router.get("/live-forward/{job_id}", response_model=LiveForwardReport)
def live_forward(job_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")], queue: Queue) -> dict:
    job, result = _experiment_job(queue, job_id, "live_forward_report", "El informe prospectivo no existe.")
    return result | {"job_id": job_id, "result_sha256": job["result_sha256"]}


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
