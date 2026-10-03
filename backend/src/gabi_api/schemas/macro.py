from datetime import date

from gabi_api.schemas.market import WireModel


class MacroPoint(WireModel):
    series_id: str
    label: str
    unit: str  # of latest_value: «%», «p. p.», «índice», «USD»…
    change_unit: str  # of change_3m: a change between rates is in percentage points
    help: str
    latest_value: float | None
    latest_date: date | None
    change_3m: float | None


class MacroResponse(WireModel):
    items: list[MacroPoint]
    source: str = "FRED local cache"
    affects_score: bool = False
