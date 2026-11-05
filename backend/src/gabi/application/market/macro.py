"""Cached macro context; a query never contacts FRED."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Protocol

from gabi.domain.market import macro_trend
from gabi.domain.market.macro_labels import labels

# Published units of each series' level and of its change. The legacy labels are ambiguous on
# screen: «puntos» are percentage points, a change between rates is in percentage points, and
# the Fed balance in «millones $» is published in dollars so it can be read as «billones».
UNITS = {"%": ("%", "p. p."), "% interanual": ("% interanual", "p. p."), "puntos": ("p. p.", "p. p."),
         "puntos %": ("%", "p. p."), "índice": ("índice", "índice"), "millones $": ("USD", "USD"),
         "personas": ("personas", "personas")}
SCALE = {"millones $": 1e6}


class MacroRepository(Protocol):
    def value_at_or_before(self, series_id: str, cutoff: date | None) -> tuple[date, float] | None: ...
    def history(self, series_id: str, start: date) -> list[tuple[date, float]]: ...


class MacroQueries:
    def __init__(self, repository: MacroRepository, metadata: dict[str, dict],
                 key_configured: Callable[[], bool] = lambda: False):
        self.repository, self.metadata, self.key_configured = repository, metadata, key_configured

    def snapshot(self) -> list[dict]:
        rows = []
        for series_id, meta in self.metadata.items():
            latest = self.repository.value_at_or_before(series_id, None)
            older = self.repository.value_at_or_before(series_id, latest[0] - timedelta(days=90)) if latest else None
            unit, change_unit = UNITS.get(meta["unit"], (meta["unit"], meta["unit"]))
            scale = SCALE.get(meta["unit"], 1)
            rows.append({"series_id": series_id, "label": meta["label"], "unit": unit, "change_unit": change_unit,
                         "help": meta["help"], "frequency": meta["frequency"], "aggregation": meta["aggregation"],
                         "home": meta["home"], "block": meta["block"],
                         "latest_value": latest[1] * scale if latest else None,
                         "latest_date": latest[0] if latest else None,
                         "change_3m": (latest[1] - older[1]) * scale if latest and older else None,
                         "trend": self._trend(series_id, latest, unit, scale)})
        return rows

    def _trend(self, series_id: str, latest: tuple[date, float] | None, unit: str, scale: float) -> dict:
        """Monthly points of its last 5 years and their reading (#327); nothing without data."""
        if latest is None:
            return macro_trend.read([], unit)
        start = date(latest[0].year - 5, latest[0].month, 1)
        result = macro_trend.read(self.repository.history(series_id, start), unit)
        if scale != 1:  # The text never quotes these units; the points and the median follow the level's unit.
            result["points"] = [point | {"value": point["value"] * scale} for point in result["points"]]
            for key in ("median", "start", "end"):
                if result.get(key) is not None:
                    result[key] *= scale
        return result

    def labels(self, rows: list[dict]) -> list[dict]:
        """One label in words per block (#309), from the rows `snapshot` already read."""
        return labels(rows)
