from typing import Literal

from pydantic import BaseModel, Field

from gabi_api.schemas.decisions import DecisionPolicy


class BacktestOptions(BaseModel):
    """Exact per-engine keys are enforced by the application use case."""

    model_config = {"extra": "forbid"}

    months: Literal[1, 3, 6, 12]
    top_n: int = Field(ge=1, le=50)
    rotation_hurdle_points: float = Field(ge=0, le=100)
    cost_bps: float | None = Field(default=None, ge=0, le=500)
    universe_size: Literal[50, 100, 500] | None = None
    mode: Literal["validation", "fast_dev"] | None = None
    max_symbols: Literal[50, 100, 200] | None = None
    initial_capital: float | None = Field(default=None, ge=1_000, le=100_000_000)
    commission_usd: float | None = Field(default=None, ge=0, le=100)
    spread_bps: float | None = Field(default=None, ge=0, le=500)


class ResearchLogRequest(BaseModel):
    """Register one finished V1/V2 backtest in Research Lab."""

    model_config = {"extra": "forbid"}

    source_job_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    stage: Literal["RESEARCH", "IN_SAMPLE", "OUT_OF_SAMPLE", "LIVE_FORWARD"]
    hypothesis_registered: bool
    family: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2_000)


class FactorContrastRequest(BaseModel):
    """Fama-French 5 + Momentum contrast of one finished V1 backtest."""

    model_config = {"extra": "forbid"}

    source_job_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    hac_lags: int | None = Field(default=None, ge=0, le=400)


class PreparationRequest(BaseModel):
    """Download what a reconstruction date or a backtest range needs; exact keys are checked later."""

    model_config = {"extra": "forbid"}

    scope: Literal["date", "backtest"]
    universe_limit: Literal[15, 50] | None = None
    months: Literal[1, 3, 6, 12] | None = None
    max_symbols: Literal[50, 100, 200, 500] | None = None


class OutcomesRequest(BaseModel):
    """Later return of the leaders of one finished historical ranking."""

    model_config = {"extra": "forbid"}

    source_job_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    top_n: int = Field(ge=1, le=50)
    cost_bps: float = Field(default=0.0, ge=0, le=100)


class ExperimentAnalysisRequest(BaseModel):
    """PBO/CSCV over 2-20 logged experiments, or a block bootstrap of one (optionally paired)."""

    model_config = {"extra": "forbid"}

    experiment_ids: list[int] | None = Field(default=None, min_length=2, max_length=20)
    experiment_id: int | None = Field(default=None, ge=1)
    benchmark_id: int | None = Field(default=None, ge=1)


class LiveReportRequest(BaseModel):
    """LIVE_FORWARD paper report of one model version, from the frozen prospective ledger."""

    model_config = {"extra": "forbid"}

    model_version: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")


class BlindJobRequest(BaseModel):
    """One blind validation: record today's due rebalance, compute revealed performance or export it."""

    model_config = {"extra": "forbid"}

    validation_id: int = Field(ge=1, le=1_000_000)


class PortfolioLabOptions(BaseModel):
    """The Streamlit Portfolio Lab form: schemes over the same point-in-time candidates."""

    model_config = {"extra": "forbid"}

    months: Literal[1, 3, 6, 12]
    top_n: int = Field(ge=2, le=50)
    initial_capital: float = Field(ge=1_000, le=10_000_000)
    schemes: list[Literal["equal_weight", "inverse_vol", "min_variance", "score_weighted", "score_constrained",
                          "risk_parity"]] = Field(min_length=1, max_length=6)
    mode: Literal["validation", "fast_dev"]
    max_symbols: Literal[50, 100, 200] | None = None


class CompanySyncRequest(BaseModel):
    """Download one company's earnings surprises, consensus estimates or Form 4 lines (the old Ficha buttons)."""

    model_config = {"extra": "forbid"}

    symbol: str = Field(pattern=r"^[A-Za-z0-9^][A-Za-z0-9^.\-]{0,19}$")
    dataset: Literal["surprises", "estimates", "insiders"]


class DataUpdateRequest(BaseModel):
    """The old «Actualizar datos»: a universe size (50, 150 or full) or the failed symbols to retry."""

    model_config = {"extra": "forbid"}

    universe_limit: Literal[50, 150] | None = None
    force: bool = False
    symbols: list[str] | None = Field(default=None, min_length=1, max_length=1000)


class DataHealthRequest(BaseModel):
    """The old «Calidad de los datos»: universe, one company, identities or the 2010-2015 archive."""

    model_config = {"extra": "forbid"}

    scope: Literal["universe", "company", "identities", "archive", "archive_members", "archive_prices"]
    symbol: str | None = Field(default=None, max_length=20)
    as_of: str | None = Field(default=None, max_length=10)
    source: str | None = Field(default=None, max_length=200)


class CreateJobRequest(BaseModel):
    kind: Literal["refresh", "symbols", "quality", "backtest", "sim_result", "sim_compare", "decision_plan", "filing_check", "historical_ranking", "factor_analysis", "estimate_analysis", "backtest_v1", "backtest_v2", "backtest_register", "backtest_factors", "prepare_history", "historical_outcomes", "experiment_pbo", "experiment_bootstrap", "live_forward_report", "blind_rebalance", "blind_performance", "blind_export", "portfolio_lab", "company_sync", "data_update", "data_health", "sim_prices"]
    idempotency_key: str = Field(min_length=8, max_length=100)
    symbols: list[str] = Field(default_factory=list, max_length=10)
    start: str | None = None
    end: str | None = None
    portfolio_id: int | None = Field(default=None, ge=1, le=1_000_000)
    decision_policy: DecisionPolicy | None = None
    holdings_text: str | None = Field(default=None, max_length=5000)
    snapshot_id: int | None = Field(default=None, ge=1, le=1_000_000)
    factor_months: Literal[1, 3, 6, 12] | None = None
    factor_mode: Literal["validation", "fast_dev"] | None = None
    factor_max_symbols: Literal[50, 100, 200] | None = None
    backtest_options: BacktestOptions | None = None
    research_log: ResearchLogRequest | None = None
    factor_contrast: FactorContrastRequest | None = None
    preparation: PreparationRequest | None = None
    outcomes: OutcomesRequest | None = None
    experiment_analysis: ExperimentAnalysisRequest | None = None
    live_report: LiveReportRequest | None = None
    blind: BlindJobRequest | None = None
    portfolio_options: PortfolioLabOptions | None = None
    company: CompanySyncRequest | None = None
    update: DataUpdateRequest | None = None
    health: DataHealthRequest | None = None


class JobEvent(BaseModel):
    at: str
    message: str


class JobResponse(BaseModel):
    id: str
    kind: str
    parameters: dict
    origin: str
    status: str
    progress: int
    phase: str
    cancel_requested: bool
    created_at: str
    started_at: str | None
    finished_at: str | None
    error_code: str | None
    result_ref: str | None
    result_sha256: str | None
    checkpoint: dict
    events: list[JobEvent] | None = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]


class LocalSettingsResponse(BaseModel):
    keys: dict[str, bool]
    scheduler: str = "local"


class BlindRebalanceNotice(BaseModel):
    id: int
    name: str
    due: str
    days: int
    overdue: bool


class SmallmidNotice(BaseModel):
    data_frozen: bool
    tiingo_complete: bool
    freeze_deadline: str
    analyzed: bool


class NoticesResponse(BaseModel):
    """Home notices: blind rebalances due within a week and the state of the #44 analysis."""

    blind_rebalances: list[BlindRebalanceNotice]
    blind_available: bool
    smallmid: SmallmidNotice | None
