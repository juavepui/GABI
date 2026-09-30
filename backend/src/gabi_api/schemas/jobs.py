from typing import Literal

from pydantic import BaseModel, Field

from gabi_api.schemas.decisions import DecisionPolicy


class CreateJobRequest(BaseModel):
    kind: Literal["refresh", "symbols", "quality", "backtest", "sim_result", "sim_compare", "decision_plan", "filing_check", "historical_ranking"]
    idempotency_key: str = Field(min_length=8, max_length=100)
    symbols: list[str] = Field(default_factory=list, max_length=10)
    start: str | None = None
    end: str | None = None
    portfolio_id: int | None = Field(default=None, ge=1, le=1_000_000)
    decision_policy: DecisionPolicy | None = None
    holdings_text: str | None = Field(default=None, max_length=5000)
    snapshot_id: int | None = Field(default=None, ge=1, le=1_000_000)


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
