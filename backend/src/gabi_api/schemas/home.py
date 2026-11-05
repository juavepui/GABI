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


class SummarySentence(BaseModel):
    """One plain-language sentence of «Tu resumen de hoy»; `values` holds the data every number comes from."""

    kind: Literal["data", "moves", "other_model", "unscored", "target", "earnings"]
    tone: Literal["good", "bad", "neutral"]
    text: str
    symbols: list[str]
    link: str | None
    values: dict[str, Any]


class HomeSummary(BaseModel):
    """«Tu resumen de hoy» (#307): templates, no AI. `no_companies`: the user follows nothing yet."""

    status: Literal["ready", "no_companies"]
    followed_count: int
    watched_count: int
    held_count: int
    score_points: float
    rank_places: int
    window_days: int
    sentences: list[SummarySentence]


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
    summary: HomeSummary | None = None
