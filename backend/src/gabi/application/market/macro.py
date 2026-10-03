"""Cached macro context; a query never contacts FRED."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Protocol

# Published units of each series' level and of its change. The legacy labels are ambiguous on
# screen: «puntos» are percentage points, a change between rates is in percentage points, and
# the Fed balance in «millones $» is published in dollars so it can be read as «billones».
UNITS = {"%": ("%", "p. p."), "% interanual": ("% interanual", "p. p."), "puntos": ("p. p.", "p. p."),
         "puntos %": ("%", "p. p."), "índice": ("índice", "índice"), "millones $": ("USD", "USD")}
SCALE = {"millones $": 1e6}


class MacroRepository(Protocol):
    def value_at_or_before(self, series_id: str, cutoff: date | None) -> tuple[date, float] | None: ...


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
                         "help": meta["help"], "latest_value": latest[1] * scale if latest else None,
                         "latest_date": latest[0] if latest else None,
                         "change_3m": (latest[1] - older[1]) * scale if latest and older else None})
        return rows
