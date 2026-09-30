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


class CreateJobRequest(BaseModel):
    kind: Literal["refresh", "symbols", "quality", "backtest", "sim_result", "sim_compare", "decision_plan", "filing_check", "historical_ranking", "factor_analysis", "estimate_analysis", "backtest_v1", "backtest_v2"]
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
