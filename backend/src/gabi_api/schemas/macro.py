from datetime import date
from typing import Literal

from gabi_api.schemas.market import WireModel

Block = Literal["liquidity", "inflation_rates", "growth_jobs", "conditions"]


class MacroLabel(WireModel):
    """A block's state in words (#309), from a fixed rule on one series; context, never a signal."""

    block: Block
    title: str
    label: str
    tone: Literal["good", "bad", "neutral"]
    series_id: str | None  # None: no data stored for the series the rule needs
    value: float | None  # the value the rule read (the Fed balance: its % change)
    date: date | None
    rule: str


class TrendPoint(WireModel):
    date: date
    value: float


class MacroTrend(WireModel):
    """Its last 5 years, one point per month, read with fixed rules (#327); context, never a forecast."""

    points: list[TrendPoint]
    months: int
    direction: Literal["up", "down", "flat"] | None  # None: fewer than 13 months stored
    level: Literal["above", "below", "usual"] | None  # against its 5-year median; None below 24 months
    median: float | None
    start: float | None = None  # value 12 months ago
    end: float | None = None
    years: int | None = None
    text: str | None


class MacroPoint(WireModel):
    series_id: str
    label: str
    unit: str  # of latest_value: «%», «p. p.», «índice», «USD»…
    change_unit: str  # of change_3m: a change between rates is in percentage points
    help: str
    frequency: Literal["daily", "weekly", "monthly"]  # how often FRED publishes a value
    # What each value is: last of the period, period average, change on a year ago, the Wednesday
    # level of a weekly balance, or the 3-month average of unemployment (Sahm).
    aggregation: Literal["end_of_period", "average", "year_over_year", "wednesday_level", "three_month_average"]
    home: bool  # shown in the Home context strip (#195)
    block: Block  # the panel group it belongs to (#309)
    latest_value: float | None
    latest_date: date | None
    change_3m: float | None
    trend: MacroTrend


class MacroResponse(WireModel):
    items: list[MacroPoint]
    labels: list[MacroLabel]
    source: str = "FRED local cache"
    affects_score: bool = False
    fred_key_configured: bool  # without it the cached series cannot be refreshed


CheckResult = Literal["pass", "caution", "fail"]


class MarketCheck(WireModel):
    """One of the four checks: its result (None without data), its plain sentence and the values it read."""

    key: Literal["trend", "breadth", "distribution", "volatility"]
    result: CheckResult | None
    title: str
    text: str
    values: dict[str, float | int | str | None]


class MarketHealthResponse(WireModel):
    """Semáforo del mercado (#308). `no_data`: fewer than 201 sessions of the index stored."""

    status: Literal["ready", "no_data"]
    version: str
    benchmark: str
    universe_count: int
    affects_score: bool = False
    sessions: int | None = None
    as_of: date | None = None
    score: float | None = None
    state: Literal["favorable", "pressure", "correction"] | None = None
    state_label: str | None = None
    days_in_state: int | None = None
    days_at_least: bool | None = None  # True: the state lasts at least the whole window counted
    history_sessions: int | None = None
    checks: list[MarketCheck] = []
