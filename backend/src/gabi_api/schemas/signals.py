from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field

from gabi_api.schemas.market import WireModel


class SaveSnapshot(WireModel):
    name: str = Field(min_length=1, max_length=80)
    top_n: int = Field(default=10, ge=1, le=30)


class Snapshot(WireModel):
    id: int
    name: str
    created_at: datetime
    as_of_date: date
    source: str
    candidates: int


class SnapshotList(WireModel):
    items: list[Snapshot]


class CompareSignals(WireModel):
    snapshot_id: int = Field(ge=1)
    rank_change: int = Field(default=5, ge=1, le=1000)
    score_change: float = Field(default=10, gt=0, le=100, allow_inf_nan=False)
    confidence_drop: float = Field(default=20, gt=0, le=100, allow_inf_nan=False)


class SignalEvent(WireModel):
    id: int | None = None
    from_snapshot_id: int | None = None
    to_snapshot_id: int | None = None
    symbol: str
    event_type: str
    severity: str
    previous_value: Any = None
    new_value: Any = None
    cause: str
    detected_at: datetime | None = None


class SignalEventList(WireModel):
    items: list[SignalEvent]
    basis: Literal["frozen_weights"] = "frozen_weights"
    status: Literal["DIAGNOSTIC", "EXPERIMENTAL"] = "DIAGNOSTIC"
    note: str = "Son cambios de datos respecto a un snapshot, no órdenes ni prueba de ventaja sobre SPY."


class EarningsEvent(WireModel):
    symbol: str
    event_date: date
    is_estimate: bool
    days_until: int


class EarningsList(WireModel):
    items: list[EarningsEvent]


class SaveFilingCheck(WireModel):
    job_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class FilingCheckSaved(WireModel):
    recorded: bool
    events: list[SignalEvent]


class SnapshotDetailRow(WireModel):
    symbol: str
    price_start: float | None
    price_now: float | None
    return_: float | None = Field(alias="return")

    model_config = {"populate_by_name": True}


class SnapshotCurvePoint(WireModel):
    date: str
    basket: float | None
    spy: float | None


class SnapshotHorizon(WireModel):
    months: int
    status: Literal["pending", "complete", "incomplete"]
    end_date: str
    available: int | None = None
    requested: int | None = None
    portfolio_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    missing: list[str] = []


class SnapshotProgress(WireModel):
    id: int
    name: str
    as_of_date: str
    created_at: str
    candidates: int
    today: str
    data_as_of: str | None
    stale: bool
    available: int
    requested: int
    portfolio_return: float | None
    benchmark_return: float | None
    excess_return: float | None
    missing: list[str]
    detail: list[SnapshotDetailRow]
    curve: list[SnapshotCurvePoint]
    horizons: list[SnapshotHorizon]


class SnapshotRename(WireModel):
    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=80)


class SnapshotRenamed(WireModel):
    id: int
    name: str
