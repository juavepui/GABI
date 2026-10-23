from typing import Any, Literal

from pydantic import BaseModel, Field

from gabi_api.schemas.market import DataResponse


class HomeTarget(BaseModel):
    symbol: str
    name: str | None
    sector: str | None
    composite_score: float
    weight_pct: float


class HomeLastUpdate(BaseModel):
    kind: str
    finished_at: str | None


class HomeSteps(BaseModel):
    fred_key: bool
    universe: bool
    data_loaded: bool | None
    updated: bool


class HomeAlert(BaseModel):
    """One thing that needs attention; `detail` carries the kind's own fields (dates, entries, error code)."""

    kind: Literal["earnings", "ex_dividend", "dividend_payment", "top_changes", "filings", "job_failed",
                  "thesis_review"]
    severity: Literal["high", "medium", "info"]
    date: str | None
    symbols: list[str]
    link: str
    detail: dict[str, Any] = Field(default_factory=dict)


class HomeResponse(BaseModel):
    """The home page. `ranking_ready=False`: the frozen ranking is not cached yet (ask again with compute)."""

    as_of: str
    model_id: str
    ranking_ready: bool
    data: DataResponse | None
    target: list[HomeTarget]
    target_positions: int
    last_update: HomeLastUpdate | None
    steps: HomeSteps
    alerts: list[HomeAlert] = Field(default_factory=list)
