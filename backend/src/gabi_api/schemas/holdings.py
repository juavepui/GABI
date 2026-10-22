"""Mi cartera (#181): real purchase lots and their read-only valuation in euros against SPY."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from gabi_api.schemas.market import WireModel
from gabi_api.schemas.portfolio import SectorWeight


class HoldingCreate(WireModel):
    symbol: str = Field(min_length=1, max_length=20)
    shares: float = Field(gt=0, le=1e9, allow_inf_nan=False)
    price: float = Field(gt=0, le=1e9, allow_inf_nan=False, description="Precio por acción en `currency`")
    purchase_date: date
    currency: Literal["USD", "EUR", "GBP"] = "USD"
    commission: float = Field(default=0, ge=0, le=1e9, allow_inf_nan=False, description="En `currency`")
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


class HoldingTotals(WireModel):
    cost_eur: float | None
    value_eur: float | None
    return_eur: float | None
    spy_return_eur: float | None
    valued: int
    positions: int
    complete: bool


class HoldingDeviation(WireModel):
    symbol: str
    weight_pct: float | None
    target_pct: float
    deviation_pp: float | None


class HoldingsSummary(WireModel):
    as_of: date
    base_currency: Literal["EUR"]
    lots: list[Holding]
    positions: list[HoldingPosition]
    totals: HoldingTotals | None
    benchmark_as_of: date | None
    deviations: list[HoldingDeviation]
    sectors: list[SectorWeight]
    missing: list[str]
    price_symbols: list[str]
    note: str = ("Valores con el último cierre en caché, sin dividendos. SPY se compra con los mismos euros en las "
                 "mismas fechas. Consultar no descarga precios; ninguna orden se envía a ningún sitio.")


def sector_weights(rows: list[dict]) -> list[SectorWeight]:
    return [SectorWeight(sector=row["sector"], positions=row["positions"], weight_percent=row["weight_pct"],
                         index_weight_percent=row["index_weight_pct"], difference_points=row["difference_pp"])
            for row in rows]
