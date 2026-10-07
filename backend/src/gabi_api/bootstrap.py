"""The only HTTP composition root. Importing it never opens application data."""
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from gabi.application.administration.data_update import KeyCommands
from gabi.application.administration.home import HomeQueries
from gabi.application.administration.jobs import Jobs
from gabi.application.administration.model import ModelCommands, ModelQueries
from gabi.application.administration.notices import Notices
from gabi.application.errors import QueryError
from gabi.application.market.analysis_prompt import AnalysisPrompt
from gabi.application.market.company_research import CompanyResearch
from gabi.application.market.evidence import EvidenceQueries
from gabi.application.market.glossary import metric_glossary, technical_terms
from gabi.application.market.glossary import terms as glossary_terms
from gabi.application.market.macro import MacroQueries
from gabi.application.market.queries import MarketQueries
from gabi.application.market.signals import SignalMonitor
from gabi.application.market.snapshots import SnapshotTracking
from gabi.application.portfolio.decisions import Decisions
from gabi.application.portfolio.journal import Journal
from gabi.application.portfolio.planning import PortfolioQueries
from gabi.application.portfolio.simulations import Simulations
from gabi.application.research.backtest_diagnostics import BacktestDiagnostics
from gabi.application.research.blind import BlindCommands, BlindValidationQueries
from gabi.application.research.catalog import ResearchCatalog
from gabi.application.research.estimates import EstimateQueries
from gabi.application.research.experiment_commands import ExperimentCommands
from gabi.application.research.experiment_statistics import ExperimentStatistics
from gabi.application.research.experiments import ExperimentQueries
from gabi.application.research.historical_queries import HistoricalQueries
from gabi.application.research.live_ledger import LiveLedgerCommands, LiveLedgerQueries
from gabi.application.research.portfolio_lab_queries import PortfolioLabQueries
from gabi.application.research.published_factors import PublishedFactorQueries
from gabi.application.research.saved_audits import SavedAuditQueries
from gabi.domain.market.freshness import last_completed_session
from gabi.domain.market.signals import compare_snapshots
from gabi.infrastructure.legacy.backtests import LegacyBacktestMath
from gabi.infrastructure.legacy.blind import LegacyBlindWriter
from gabi.infrastructure.legacy.company import LegacyCompanyMath, analysis_prompt
from gabi.infrastructure.legacy.data_update import LegacyKeyWriter
from gabi.infrastructure.legacy.evidence import LegacyEvidence
from gabi.infrastructure.legacy.experiment_log import LegacyExperimentLog
from gabi.infrastructure.legacy.experiments import LegacyExperimentMath
from gabi.infrastructure.legacy.filings import compare_cached
from gabi.infrastructure.legacy.historical import LegacyRankingQuality
from gabi.infrastructure.legacy.live_ledger import LegacyLiveLedger
from gabi.infrastructure.legacy.macro import series_metadata
from gabi.infrastructure.legacy.market import calculators, defaults, metric_blocks, metric_directions, model_policy
from gabi.infrastructure.legacy.smallmid import smallmid_freeze_deadline
from gabi.infrastructure.legacy.snapshots import LegacySnapshotMath
from gabi.infrastructure.serialization.decisions import build_decisions
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.blind import SqliteBlindStore
from gabi.infrastructure.storage.blind_plans import FileBlindPlans
from gabi.infrastructure.storage.company_research import SqliteCompanyResearch
from gabi.infrastructure.storage.decisions import SqliteDecisions
from gabi.infrastructure.storage.estimates import SqliteEstimateCaptures
from gabi.infrastructure.storage.experiments import SqliteExperiments
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi.infrastructure.storage.journal import SqliteJournal
from gabi.infrastructure.storage.keys import configured_keys
from gabi.infrastructure.storage.live_ledger import SqliteLiveLedger
from gabi.infrastructure.storage.macro import SqliteMacro
from gabi.infrastructure.storage.market import ReadOnlyMarket
from gabi.infrastructure.storage.mode import FileMode
from gabi.infrastructure.storage.published_factors import FilePublishedFactors
from gabi.infrastructure.storage.published_research import FilePublishedArtifacts, FilePublishedLedger
from gabi.infrastructure.storage.saved_audits import FileSavedAudits
from gabi.infrastructure.storage.signals import SqliteSignals
from gabi.infrastructure.storage.simulations import SqliteSimulations
from gabi.infrastructure.storage.smallmid import SmallmidFiles
from gabi.infrastructure.storage.snapshot_prices import SqliteSnapshotPrices
from gabi.infrastructure.storage.weights import FileWeights
from gabi_api.routes.decisions import router as decisions_router
from gabi_api.routes.jobs import router as jobs_router
from gabi_api.routes.journal import router as journal_router
from gabi_api.routes.macro import router as macro_router
from gabi_api.routes.market import router
from gabi_api.routes.portfolio import router as portfolio_router
from gabi_api.routes.research import router as research_router
from gabi_api.routes.signals import router as signals_router
from gabi_api.routes.simulations import router as simulations_router
from gabi_api.static import mount_frontend


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
    status: str = "error"


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "GABI"
    api_version: str = "v1"


def create_app(settings: Settings | None = None, *, today: Callable[[], date] = date.today,
               published_ledger: Path | None = None, published_factors_root: Path | None = None,
               frontend_dist: Path | None = None, saved_audits_root: Path | None = None,
               blind_plans_root: Path | None = None, session: Callable[[], date] | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    session = session or (lambda: last_completed_session(datetime.now(UTC)))
    benchmark, risk_free_rate = defaults()
    policy = model_policy()
    repository = ReadOnlyMarket(settings, calculators(), policy, benchmark, risk_free_rate)
    model_queries = ModelQueries(repository, policy)
    market = MarketQueries(repository, model_queries, today, session)
    model_commands = ModelCommands(model_queries, FileWeights(settings.data_dir), FileMode(settings.data_dir))
    jobs = Jobs(SqliteJobs(settings.data_dir), lambda: model_queries.model().mode == "RESEARCH")
    portfolio = PortfolioQueries(repository, policy, today)
    journal = Journal(SqliteJournal(settings.data_dir))
    macro = MacroQueries(SqliteMacro(settings.data_dir), series_metadata(),
                         lambda: bool(configured_keys(settings.data_dir).get("fred")))
    signals = SignalMonitor(SqliteSignals(settings.data_dir), repository, policy, today,
                            compare_snapshots, compare_cached, jobs)
    simulations = Simulations(SqliteSimulations(settings.data_dir), today)
    decisions = Decisions(repository, SqliteDecisions(settings.data_dir), policy, today, build_decisions, jobs)
    ledger_path = published_ledger or settings.data_dir.parent / "docs" / "search-ledger" / "ledger.json"
    ledger = FilePublishedLedger(ledger_path)
    # The ledger lives in <checkout>/docs/search-ledger: its references are relative to the checkout.
    research_catalog = ResearchCatalog(ledger, FilePublishedArtifacts(ledger_path.parents[2], ledger))
    published_factors = PublishedFactorQueries(FilePublishedFactors(published_factors_root or settings.data_dir.parent))
    blind_validations = BlindValidationQueries(SqliteBlindStore(settings.data_dir), today,
                                               FileBlindPlans(blind_plans_root or settings.data_dir.parent))
    estimate_queries = EstimateQueries(SqliteEstimateCaptures(settings.data_dir))
    experiment_store = SqliteExperiments(settings.data_dir)
    experiments = ExperimentQueries(experiment_store, lambda: model_queries.model().mode == "RESEARCH")
    experiment_statistics = ExperimentStatistics(experiment_store, lambda: model_queries.model().mode == "RESEARCH",
                                                 LegacyExperimentMath())
    backtest_diagnostics = BacktestDiagnostics(jobs, LegacyBacktestMath())
    historical_queries = HistoricalQueries(jobs, LegacyRankingQuality())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            market.close()

    # Python 3.12 and 3.13 name HTTP 422 differently. Keep the public schema stable.
    descriptions = {403: "Modo no permitido", 404: "Empresa no encontrada", 409: "Datos cambiados",
                    422: "Consulta no válida", 500: "Error interno", 503: "Datos no disponibles"}
    errors: dict[int | str, dict[str, Any]] = {
        status: {"model": ErrorResponse, "description": description}
        for status, description in descriptions.items()
    }
    app = FastAPI(title="GABI local API", version="1.0.0", lifespan=lifespan, responses=errors)
    app.state.market = market
    app.state.metric_directions = metric_directions()
    app.state.analysis_prompt = AnalysisPrompt(market, analysis_prompt)
    app.state.metric_glossary = {"blocks": metric_glossary(*metric_blocks()), "terms": glossary_terms(),
                                 "glossary": technical_terms()}
    app.state.evidence = EvidenceQueries(market, LegacyEvidence(), LegacyRankingQuality())
    app.state.jobs = jobs
    app.state.portfolio = portfolio
    app.state.journal = journal
    app.state.macro = macro
    app.state.signals = signals
    app.state.company_research = CompanyResearch(
        SqliteCompanyResearch(settings.data_dir), repository.company_events,
        lambda symbol: signals.compare_filings(symbol, *signals.repository.filing_facts(symbol)),
        LegacyCompanyMath(), today)
    app.state.snapshot_tracking = SnapshotTracking(
        SqliteSignals(settings.data_dir), lambda day: SqliteSnapshotPrices(settings.data_dir, day),
        LegacySnapshotMath(), today)
    app.state.simulations = simulations
    app.state.decisions = decisions
    app.state.research_catalog = research_catalog
    app.state.published_factors = published_factors
    app.state.blind_validations = blind_validations
    app.state.blind_commands = BlindCommands(blind_validations, LegacyBlindWriter(settings.data_dir),
                                             lambda: model_queries.model().mode == "RESEARCH")
    app.state.estimate_queries = estimate_queries
    app.state.experiments = experiments
    app.state.experiment_statistics = experiment_statistics
    research_mode = lambda: model_queries.model().mode == "RESEARCH"  # noqa: E731
    app.state.live_ledger = LiveLedgerQueries(SqliteLiveLedger(settings.data_dir), research_mode)

    def live_report(job_id: str) -> dict:
        if jobs.get(job_id)["kind"] != "live_forward_report":
            raise QueryError("job_not_found", "El informe prospectivo no existe.", 404)
        return jobs.result(job_id)  # Research mode and the stored SHA-256 are checked here.

    app.state.live_ledger_commands = LiveLedgerCommands(app.state.live_ledger,
                                                        LegacyLiveLedger(settings.data_dir), live_report)
    app.state.saved_audits = SavedAuditQueries(FileSavedAudits(saved_audits_root or settings.data_dir.parent),
                                               lambda: model_queries.model().mode == "RESEARCH")
    app.state.experiment_commands = ExperimentCommands(LegacyExperimentLog(settings.data_dir),
                                                       lambda: model_queries.model().mode == "RESEARCH")
    app.state.backtest_diagnostics = backtest_diagnostics
    app.state.historical_queries = historical_queries
    app.state.portfolio_lab = PortfolioLabQueries(jobs, LegacyBacktestMath())
    app.state.settings = settings
    app.state.model_commands = model_commands
    app.state.home = HomeQueries(repository, policy, jobs, lambda: configured_keys(settings.data_dir),
                                 lambda: (settings.data_dir / "sp500_constituents.csv").is_file(), today, session)
    app.state.notices = Notices(blind_validations, SmallmidFiles(settings.data_dir, settings.data_dir.parent,
                                                               smallmid_freeze_deadline), today)
    app.state.key_commands = KeyCommands(LegacyKeyWriter(settings.data_dir),
                                         lambda: configured_keys(settings.data_dir))
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST"],
                       allow_headers=["Accept", "Content-Type"], allow_credentials=False)

    def error(code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(status_code=status, content=ErrorResponse(error=ErrorDetail(code=code, message=message)).model_dump())

    @app.exception_handler(QueryError)
    async def query_error(request: Request, exc: QueryError) -> JSONResponse:
        return error(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error("invalid_request", "Los parámetros de consulta no son válidos.", 422)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return error("internal_error", "No se puede completar la consulta local.", 500)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error("http_error", "La ruta o el método solicitado no está disponible.", exc.status_code)

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["administration"])
    def health() -> HealthResponse:
        return HealthResponse()

    app.include_router(router)
    app.include_router(jobs_router)
    app.include_router(portfolio_router)
    app.include_router(journal_router)
    app.include_router(macro_router)
    app.include_router(signals_router)
    app.include_router(simulations_router)
    app.include_router(decisions_router)
    app.include_router(research_router)
    if frontend_dist is not None:
        mount_frontend(app, frontend_dist)
    return app


def main() -> None:
    import uvicorn

    # No host option/environment override: the supported launcher only listens locally.
    uvicorn.run(create_app(), host="127.0.0.1", port=8000, access_log=False)


if __name__ == "__main__":
    main()
