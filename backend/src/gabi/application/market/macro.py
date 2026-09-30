"""Cached macro context; a query never contacts FRED."""

from datetime import date, timedelta
from typing import Protocol


class MacroRepository(Protocol):
    def value_at_or_before(self, series_id: str, cutoff: date | None) -> tuple[date, float] | None: ...


class MacroQueries:
    def __init__(self, repository: MacroRepository, metadata: dict[str, dict]):
        self.repository, self.metadata = repository, metadata

    def snapshot(self) -> list[dict]:
        rows = []
        for series_id, meta in self.metadata.items():
            latest = self.repository.value_at_or_before(series_id, None)
            older = self.repository.value_at_or_before(series_id, latest[0] - timedelta(days=90)) if latest else None
            rows.append({"series_id": series_id, "label": meta["label"], "unit": meta["unit"],
                         "help": meta["help"], "latest_value": latest[1] if latest else None,
                         "latest_date": latest[0] if latest else None,
                         "change_3m": latest[1] - older[1] if latest and older else None})
        return rows
