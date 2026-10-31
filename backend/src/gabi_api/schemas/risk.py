"""Issuer risk panel and the investable portfolio policy (#248)."""

from datetime import date, datetime

from pydantic import Field

from gabi_api.schemas.market import WireModel


class PortfolioPolicyInput(WireModel):
    max_issuer_weight: float = Field(gt=0, le=1, description="Peso máximo por emisor (fracción)")
    max_sector_weight: float = Field(gt=0, le=1, description="Peso máximo por sector (fracción)")
    cash_weight: float = Field(default=0, ge=0, lt=1, description="Reserva de caja (fracción)")
    min_daily_dollar_volume: float = Field(default=5e6, ge=0, le=1e12, description="Volumen diario mínimo en USD")
    participation: float = Field(default=0.1, gt=0, le=1, description="Parte del volumen diario negociable")
    max_cost_share: float = Field(default=0.01, gt=0, le=0.2, description="Coste máximo de una orden (fracción)")


class PortfolioPolicyRevision(WireModel):
    revision: int
    version: str
    created_at: datetime
    profile: PortfolioPolicyInput


class PortfolioPolicyState(WireModel):
    current: PortfolioPolicyRevision | None
    revisions: list[PortfolioPolicyRevision]
    default: PortfolioPolicyInput
    version: str


class IssuerExposure(WireModel):
    issuer: str
    symbols: list[str]
    value_eur: float
    weight: float
    exceeds: bool


class GroupWeight(WireModel):
    name: str
    weight: float
    exceeds: bool | None = None


class FactorTilt(WireModel):
    score: float | None = Field(description="Media ponderada de 0 a 100")
    coverage: float


class LiquidityRow(WireModel):
    symbol: str
    value_eur: float
    daily_volume_eur: float | None
    days_to_trade: float | None
    illiquid: bool


class Exposure(WireModel):
    total_eur: float
    issuers: list[IssuerExposure]
    sectors: list[GroupWeight]
    industries: list[GroupWeight]
    listing_currency: list[GroupWeight]
    economic_currency: list[GroupWeight]
    factors: dict[str, FactorTilt]
    liquidity: list[LiquidityRow]
    breaches: list[str]


class RiskScenario(WireModel):
    id: str
    label: str
    change: float
    change_eur: float
    exceeds_tolerance: bool = Field(description="Motivo para revisar, nunca una venta automática")


class RiskStress(WireModel):
    scenarios: list[RiskScenario]
    notes: list[str]


class RiskPanel(WireModel):
    as_of: date
    policy_version: str
    policy_revision: int | None
    policy: PortfolioPolicyInput
    loss_tolerance: float
    positions: int
    unvalued: list[str]
    exposure: Exposure
    stress: RiskStress
    economic_currency_note: str


class SymbolWeight(WireModel):
    symbol: str
    weight: float


class ProposedOrder(WireModel):
    symbol: str
    shares: float
    amount_eur: float
    commission_eur: float
    fx_cost_eur: float
    gap_eur: float


class ExcludedCandidate(WireModel):
    symbol: str
    reason: str = Field(description="no_price | illiquid")


class PolicyAlternative(WireModel):
    label: str
    weights: list[SymbolWeight]
    cash: float
    issuers: list[IssuerExposure]
    sectors: list[GroupWeight]
    breaches: list[str]
    orders: list[ProposedOrder]
    residual_cash_eur: float
    costs_eur: float
    unfunded: list[str]


class PolicyProposal(WireModel):
    as_of: date
    policy_version: str
    policy_revision: int | None
    n_positions: int
    contribution_eur: float
    euros_per_dollar: float
    excluded: list[ExcludedCandidate]
    outside_target: list[str]
    alternatives: list[PolicyAlternative] = Field(description="Órdenes propuestas: GABI no las envía")
