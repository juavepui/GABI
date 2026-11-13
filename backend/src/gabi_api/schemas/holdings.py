"""Mi cartera (#181, #294): real purchases, sales and dividends and their read-only valuation in euros."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from gabi_api.schemas.market import WireModel
from gabi_api.schemas.portfolio import SectorWeight


class HoldingCreate(WireModel):
    symbol: str = Field(min_length=1, max_length=20)
    kind: Literal["buy", "sell", "dividend"] = Field(default="buy", description="Compra, venta o dividendo cobrado")
    shares: float = Field(default=0, ge=0, le=1e9, allow_inf_nan=False, description="0 en un dividendo")
    price: float = Field(gt=0, le=1e9, allow_inf_nan=False,
                         description="Precio por acción en `currency`; en un dividendo, el importe bruto cobrado")
    purchase_date: date
    basis_date: date | None = Field(default=None, description="Fecha de la base de acciones y precio; "
                                   "vacío = cantidades y precio originales del movimiento")
    currency: Literal["USD", "EUR", "GBP"] = "USD"
    commission: float = Field(default=0, ge=0, le=1e9, allow_inf_nan=False, description="En `currency`")
    withholding: float = Field(default=0, ge=0, le=1e9, allow_inf_nan=False,
                               description="Retención sobre un dividendo, en `currency`")
    fx_rate: float | None = Field(default=None, gt=0, le=1e6, allow_inf_nan=False,
                                  description="Euros por unidad de `currency` que aplicó el bróker; vacío = caché")
    note: str | None = Field(default=None, max_length=200)


class Holding(HoldingCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class HoldingList(WireModel):
    items: list[Holding]


class HoldingDeleted(WireModel):
    deleted: bool


class HoldingImport(WireModel):
    csv: str = Field(min_length=1, max_length=100_000)


class HoldingImportResult(WireModel):
    imported: int
    ids: list[int]


class HoldingPosition(WireModel):
    symbol: str
    sector: str | None
    in_target: bool
    currency: Literal["USD", "EUR", "GBP"]
    shares: float
    lots: int
    first_purchase: date
    average_price: float | None
    price: float | None
    price_date: date | None
    cost: float = Field(description="Coste con comisiones, en `currency`")
    value: float | None
    price_return: float | None = Field(description="Rentabilidad de precio en `currency`, sin dividendos")
    spy_return_usd: float | None
    cost_eur: float | None
    value_eur: float | None
    return_eur: float | None
    spy_value_eur: float | None
    spy_return_eur: float | None
    weight_pct: float | None
    status: Literal["ok", "missing_price", "missing_fx"]
    realized_eur: float | None = Field(description="Ganancia realizada con las ventas, a coste medio")
    dividends_eur: float | None = Field(description="Dividendos cobrados, netos de retención")
    sales: int
    dividends: int


class HoldingClosed(WireModel):
    symbol: str
    currency: Literal["USD", "EUR", "GBP"]
    realized_eur: float | None
    dividends_eur: float | None
    sales: int
    dividends: int


class HoldingTotals(WireModel):
    cost_eur: float | None
    value_eur: float | None
    return_eur: float | None
    spy_return_eur: float | None
    realized_eur: float | None
    dividends_eur: float | None
    valued: int
    positions: int
    complete: bool


class HoldingDeviation(WireModel):
    symbol: str
    weight_pct: float | None
    target_pct: float
    deviation_pp: float | None


class HoldingWarning(WireModel):
    symbol: str
    reason: Literal['unverified_actions']
    message: str


class HoldingsSummary(WireModel):
    as_of: date
    base_currency: Literal["EUR"]
    lots: list[Holding]
    positions: list[HoldingPosition]
    closed: list[HoldingClosed]
    totals: HoldingTotals | None
    benchmark_as_of: date | None
    deviations: list[HoldingDeviation]
    sectors: list[SectorWeight]
    missing: list[str]
    price_symbols: list[str]
    warnings: list[HoldingWarning] = []
    note: str = ("Valores con el último cierre en caché. Las ventas y los dividendos cobrados se muestran aparte "
                 "(ganancia realizada y dividendos netos). SPY se compra con los mismos euros en las mismas fechas. "
                 "Consultar no descarga precios; ninguna orden se envía a ningún sitio.")


class PerformancePoint(WireModel):
    date: date
    value_eur: float
    nav: float = Field(description="Valor de una participación: base 1 el primer día")


class PerformanceRisk(WireModel):
    start: date
    end: date
    sessions: int
    final_value_eur: float
    net_contributed_eur: float = Field(description="Compras − ventas − dividendos netos, en euros")
    twr: float = Field(description="Rentabilidad ponderada por tiempo: no la cambian aportaciones ni retiradas")
    twr_annualised: float | None
    money_weighted: float | None = Field(description="Rentabilidad anual del dinero invertido (TIR); "
                                                     "vacía con menos de un año")
    max_drawdown: float
    peak_date: date | None
    trough_date: date | None
    recovered_date: date | None
    volatility: float | None = Field(description="Desviación típica anualizada de los retornos diarios")
    series: list[PerformancePoint]


class PerformanceBenchmark(WireModel):
    status: Literal["ok", "missing_prices"]
    start: date | None = None
    end: date | None = None
    sessions: int | None = None
    final_value_eur: float | None = None
    net_contributed_eur: float | None = None
    twr: float | None = None
    twr_annualised: float | None = None
    money_weighted: float | None = None
    max_drawdown: float | None = None
    peak_date: date | None = None
    trough_date: date | None = None
    recovered_date: date | None = None
    volatility: float | None = None
    series: list[PerformancePoint] = []
    shortfall_eur: float | None = None
    missing: list[date] = []
    missing_sessions: int | None = None


class AttributionPosition(WireModel):
    symbol: str
    sector: str | None
    gain_eur: float
    contribution_pp: float
    open: bool


class AttributionSector(WireModel):
    sector: str
    gain_eur: float
    contribution_pp: float


class PerformanceAttribution(WireModel):
    status: Literal["ok", "no_purchases"]
    bought_eur: float | None = None
    gain_eur: float | None = None
    return_on_bought: float | None = None
    positions: list[AttributionPosition] = []
    sectors: list[AttributionSector] = []


class PerformanceGap(WireModel):
    date: date
    symbols: list[str]


class PerformanceBlocked(WireModel):
    id: int | None
    symbol: str
    date: date
    kind: Literal["buy", "sell", "dividend"]
    reason: Literal["missing_fx", "after_last_session"]


class HoldingsPerformance(WireModel):
    version: str
    as_of: date
    base_currency: Literal["EUR"]
    status: Literal["ok", "blocked", "no_movements", "no_complete_session"]
    portfolio: PerformanceRisk | None = None
    benchmark: PerformanceBenchmark | None = None
    attribution: PerformanceAttribution | None = None
    gaps: list[PerformanceGap] = []
    gap_sessions: int = 0
    blocked: list[PerformanceBlocked] = []
    pending_eur: float = 0.0
    warnings: list[HoldingWarning] = []
    note: str = ("Valor diario con los cierres y cambios guardados; los días sin precio se listan y no se "
                 "rellenan. El S&P 500 (SPY con dividendos reinvertidos, en euros) recibe el mismo dinero los "
                 "mismos días. El pasado no garantiza el futuro.")


def sector_weights(rows: list[dict]) -> list[SectorWeight]:
    return [SectorWeight(sector=row["sector"], positions=row["positions"], weight_percent=row["weight_pct"],
                         index_weight_percent=row["index_weight_pct"], difference_points=row["difference_pp"])
            for row in rows]
