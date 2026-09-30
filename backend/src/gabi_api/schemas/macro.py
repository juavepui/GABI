from datetime import date

from gabi_api.schemas.market import WireModel


class MacroPoint(WireModel):
    series_id: str
    label: str
    unit: str
    help: str
    latest_value: float | None
    latest_date: date | None
    change_3m: float | None


class MacroResponse(WireModel):
    items: list[MacroPoint]
    source: str = "FRED local cache"
    affects_score: bool = False
