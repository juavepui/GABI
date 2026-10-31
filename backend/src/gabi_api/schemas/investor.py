"""Investor profile and the S&P 500 benchmark in EUR with identical contributions (#244)."""

from datetime import date, datetime

from pydantic import Field

from gabi_api.schemas.market import WireModel


class InvestorProfileInput(WireModel):
    initial_eur: float = Field(ge=0, le=1e9, allow_inf_nan=False)
    monthly_eur: float = Field(default=0, ge=0, le=1e8, allow_inf_nan=False)
    horizon_months: int = Field(ge=1, le=600, description="Horizonte de evaluación de GABI")
    loss_tolerance: float = Field(gt=0, lt=1, description="Umbral de revisión (fracción), no una garantía")
    capital_needed_by: date | None = Field(default=None, description="Cuándo se necesita el dinero, si se sabe")
    tax_residence: str | None = Field(default=None, max_length=2,
                                      description="ISO 3166; la fiscalidad solo se aplica si está confirmada")
    commission_fixed_eur: float = Field(default=0, ge=0, le=1000, allow_inf_nan=False)
    commission_pct: float = Field(default=0, ge=0, lt=0.1, description="Fracción del importe")
    fx_cost_pct: float = Field(default=0, ge=0, lt=0.1, description="Fracción del importe convertido")
    min_order_eur: float = Field(default=0, ge=0, le=1e6, allow_inf_nan=False)
    fractional: bool = True


class InvestorProfileRevision(WireModel):
    revision: int
    version: str
    created_at: datetime
    profile: InvestorProfileInput


class InvestorProfileState(WireModel):
    current: InvestorProfileRevision | None
    revisions: list[InvestorProfileRevision]


class BenchmarkSource(WireModel):
    symbol: str
    series: str
    provider: str
    vehicle: str
    fx: str
    first_price: date
    last_price: date
    first_fx: date
    last_fx: date


class BenchmarkPerformance(WireModel):
    status: str
    start: date | None = None
    end: date | None = None
    contributed_eur: float | None = None
    final_value_eur: float | None = None
    costs_eur: float | None = None
    pending_eur: float | None = None
    twr: float | None = Field(default=None, description="Rentabilidad ponderada por tiempo (habilidad)")
    twr_annualised: float | None = None
    xirr: float | None = Field(default=None, description="Rentabilidad ponderada por dinero (experiencia)")
    max_drawdown: float | None = Field(default=None, description="Sobre el NAV unitizado: el dinero nuevo no la oculta")
    current_drawdown: float | None = None
    max_loss_on_contributions: float | None = None
    max_euros_lost: float | None = None
    euros_at_risk_at_tolerance: float | None = None
    review_threshold_reached_on: date | None = Field(default=None, description="Revisión, nunca venta automática")


class PendingContribution(WireModel):
    date: date
    amount_eur: float


class BenchmarkPoint(WireModel):
    date: date
    value_eur: float
    contributed_eur: float


class BenchmarkVehicle(WireModel):
    id: str
    symbol: str
    label: str
    currency: str
    theoretical: bool = Field(description="Índice sin costes; no es invertible")
    status: str = Field(description="ok | missing_prices")
    first_price: date | None
    last_price: date | None
    performance: BenchmarkPerformance | None


class InvestorBenchmarkResult(WireModel):
    as_of: date
    start: date
    profile_revision: int
    profile_version: str
    capital_need_before_horizon: bool | None
    source: BenchmarkSource
    performance: BenchmarkPerformance
    pending: list[PendingContribution]
    series: list[BenchmarkPoint]
    vehicles: list[BenchmarkVehicle] = Field(description="Las mismas aportaciones en el índice TR y en un ETF Acc")


class ExcludedLot(WireModel):
    id: int | None
    symbol: str
    purchase_date: date
    reason: str = Field(description="missing_price | missing_fx | after_last_session")


class BenchmarkComparison(WireModel):
    status: str
    wealth_difference_eur: float | None = None
    twr_difference: float | None = None
    xirr_difference: float | None = None
    max_drawdown_difference: float | None = None


class HoldingsBenchmarkResult(WireModel):
    as_of: date
    profile_revision: int
    profile_version: str
    source: BenchmarkSource
    portfolio: BenchmarkPerformance = Field(description="Cierre ajustado: rentabilidad total, no solo precio")
    benchmark: BenchmarkPerformance
    comparison: BenchmarkComparison
    excluded: list[ExcludedLot]
    incomplete_sessions: int
    portfolio_series: list[BenchmarkPoint]
    benchmark_series: list[BenchmarkPoint]
