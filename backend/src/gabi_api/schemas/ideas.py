from typing import Any, Literal

from pydantic import Field

from gabi_api.schemas.market import WireModel


class IdeaEventCreate(WireModel):
    kind: Literal["revisada", "retirada", "cerrada", "corregida"]
    text: str = Field(default="", max_length=2000, description="Revisión o corrección")
    reason: str = Field(default="", max_length=2000, description="Por qué se retira")
    outcome: Literal["acertada", "parcial", "fallida"] | None = None
    cause: str = Field(default="", max_length=2000, description="Causa del resultado al cerrar")
    executed: bool = Field(default=False, description="Si llegó a invertirse")
    corrects: int | None = Field(default=None, ge=1, description="Evento que se corrige")


class IdeaNoteText(WireModel):
    text: str = Field(min_length=1, max_length=2000)


class IdeaState(WireModel):
    status: Literal["abierta", "retirada", "cerrada"]
    published_on: str
    ended_on: str | None
    outcome: dict[str, Any] | None
    reviews: int
    corrections: int


class IdeaEvaluation(WireModel):
    status: Literal["ok", "insufficient_prices"]
    missing: list[str] | None = None
    start: str | None = None
    end: str | None = None
    days: int | None = None
    sessions: int | None = None
    return_net: float | None = Field(default=None, description="Rentabilidad total en EUR neta de costes de ida y vuelta")
    costs_included: bool | None = None
    index_return: float | None = Field(default=None, description="S&P 500 en EUR en las mismas fechas")
    excess: float | None = None
    max_drawdown: float | None = None
    index_max_drawdown: float | None = None


class IdeaEvent(WireModel):
    idea_id: int
    sequence: int
    kind: str
    recorded_at: str
    payload: dict[str, Any]
    previous_sha256: str | None
    sha256: str


class IdeaNote(WireModel):
    id: int
    idea_id: int
    created_at: str
    updated_at: str
    text: str


class IdeaAlert(WireModel):
    key: str
    kind: Literal["invalidacion", "revision_dato", "ausencia", "no_evaluable", "revision_vencida", "filing",
                  "resultados", "estimaciones", "insiders", "tendencia"]
    detected_at: str
    message: str
    evidence: dict[str, Any]


class Idea(WireModel):
    idea_id: int
    pending_alerts: list[IdeaAlert] = Field(description="Alertas posteriores a la última revisión; piden revisar")
    symbol: str
    card_id: int
    review_due: str | None
    state: IdeaState
    evaluation: IdeaEvaluation
    chain_ok: bool


class IdeaDetail(Idea):
    events: list[IdeaEvent]
    notes: list[IdeaNote]
    alerts: list[IdeaAlert]


class IdeaSummary(WireModel):
    ideas: int
    open: int
    closed: int
    retired: int
    evaluated: int
    beat_index: int
    median_excess: float | None
    mean_excess: float | None
    thesis_hits: dict[str, int]
    note: str


class IdeaList(WireModel):
    version: str
    as_of: str
    items: list[Idea]
    summary: IdeaSummary
    benchmark: str
