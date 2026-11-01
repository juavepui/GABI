from datetime import date
from typing import Any, Literal

from pydantic import Field

from gabi_api.schemas.market import WireModel


class CardScenario(WireModel):
    price: float | None = None
    assumptions: str = Field(default="", max_length=2000)


class CardScenarios(WireModel):
    bear: CardScenario = Field(default_factory=CardScenario)
    base: CardScenario = Field(default_factory=CardScenario)
    bull: CardScenario = Field(default_factory=CardScenario)


class CardCatalyst(WireModel):
    description: str = Field(default="", max_length=500)
    horizon: date | None = None


class CardInvalidation(WireModel):
    description: str = Field(default="", max_length=500)
    metric: str = Field(default="", max_length=100)
    source: str = Field(default="", max_length=200)
    operator: Literal["<", "<=", ">", ">="] | None = None
    threshold: float | None = None
    persistence: int | None = Field(default=None, description="Periodos consecutivos que debe cumplirse")
    review_by: date | None = None


class CardContent(WireModel):
    thesis: list[str] = Field(default_factory=list, max_length=10, description="Tesis en un máximo de tres líneas")
    discrepancy: str = Field(default="", max_length=2000, description="Qué descuenta el mercado y por qué discrepas")
    scenarios: CardScenarios = Field(default_factory=CardScenarios)
    sensitivity: str = Field(default="", max_length=2000)
    catalysts: list[CardCatalyst] = Field(default_factory=list, max_length=10)
    risks: list[str] = Field(default_factory=list, max_length=10)
    invalidation: list[CardInvalidation] = Field(default_factory=list, max_length=10)
    confidence: Literal["baja", "media", "alta"] | None = Field(
        default=None, description="Confianza subjetiva; no es una probabilidad de beneficio")
    review_due: date | None = None
    notes: str = Field(default="", max_length=2000)


class CardCreate(WireModel):
    symbol: str = Field(min_length=1, max_length=20)
    content: CardContent = Field(default_factory=CardContent)


class CardSave(WireModel):
    content: CardContent


class CardMove(WireModel):
    target: Literal["analizada", "publicada", "descartada"]
    reason: str = Field(default="", max_length=2000)


class CardScenarioReturns(WireModel):
    bear: float | None
    base: float | None
    bull: float | None


class InvestmentCard(WireModel):
    id: int
    symbol: str
    version: int
    state: Literal["incompleta", "analizada", "publicada", "descartada"]
    created_at: date
    updated_at: date
    published_at: date | None
    discarded_at: date | None
    discard_reason: str | None
    content: CardContent
    snapshot: dict[str, Any] | None = Field(description="Inputs capturados al publicar, con fuente y fecha")
    snapshot_sha256: str | None
    missing: list[str] = Field(description="Lo que falta para publicar; vacío si está completa")
    scenario_returns: CardScenarioReturns = Field(description="Movimiento de cada escenario sobre el precio publicado")
    version_rules: str
    not_a_probability: str


class InvestmentCardList(WireModel):
    items: list[InvestmentCard]
