"""Empresas seguidas (#182): followed companies, their note and the read-only view from the local cache."""

from datetime import date, datetime

from pydantic import Field

from gabi_api.schemas.checklist import ChecklistSummary
from gabi_api.schemas.market import WireModel


class WatchlistNote(WireModel):
    note: str | None = Field(default=None, max_length=500)


class WatchlistCreate(WatchlistNote):
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9^][A-Za-z0-9^.\-]*$")


class WatchlistEntry(WireModel):
    symbol: str
    added_at: datetime
    note: str | None
    model_id: str | None
    score_at_add: float | None = Field(description="Score del modelo congelado al añadirla · 0 a 100")
    rank_at_add: int | None = Field(description="Posición global al añadirla, antes de filtros")
    updated_at: datetime


class WatchlistSymbols(WireModel):
    symbols: list[str]


class WatchlistDeleted(WireModel):
    deleted: bool


class WatchlistRow(WireModel):
    symbol: str
    added_at: datetime
    note: str | None
    name: str | None
    sector: str | None
    in_ranking: bool
    composite_score: float | None = Field(description="Score actual del modelo congelado · 0 a 100")
    rank: int | None = Field(description="Posición global actual, antes de filtros")
    score_at_add: float | None
    rank_at_add: int | None
    same_model: bool = Field(description="False si se añadió con otro modelo: entonces no hay cambio comparable")
    score_change: float | None = Field(description="Puntos de score desde que se añadió")
    rank_change: int | None = Field(description="Puestos ganados desde que se añadió (negativo = perdidos)")
    next_earnings_date: date | None
    next_earnings_is_estimate: bool | None
    open_theses: int
    theses: int


class WatchlistSummary(WireModel):
    model_id: str
    ranking_ready: bool
    items: list[WatchlistRow]


class WatchlistChecklists(WireModel):
    items: dict[str, ChecklistSummary | None]
