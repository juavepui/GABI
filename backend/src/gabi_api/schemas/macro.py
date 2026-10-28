from datetime import date
from typing import Literal

from gabi_api.schemas.market import WireModel


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
    latest_value: float | None
    latest_date: date | None
    change_3m: float | None


class MacroResponse(WireModel):
    items: list[MacroPoint]
    source: str = "FRED local cache"
    affects_score: bool = False
    fred_key_configured: bool  # without it the cached series cannot be refreshed
