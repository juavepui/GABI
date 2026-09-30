"""Read blind validation seals without revealing picks or performance."""

import calendar
from collections.abc import Callable
from datetime import date
from typing import Protocol

from gabi.application.errors import QueryError
from gabi.domain.research.blind import verify_chain


class BlindStore(Protocol):
    def read_status(self) -> list[tuple[dict, list[dict]]]: ...


def _add_months(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


class BlindValidationQueries:
    def __init__(self, store: BlindStore, today: Callable[[], date]):
        self.store, self.today = store, today

    def list_status(self) -> dict:
        current = self.today()
        items = []
        for validation, periods in self.store.read_status():
            try:
                integrity = verify_chain(periods)
                unlock = date.fromisoformat(validation["unlock_date"])
                due = (_add_months(date.fromisoformat(periods[-1]["rebalance_date"]),
                                   validation["rebalance_months"])
                       if periods else date.fromisoformat(validation["start_date"]))
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise QueryError("blind_data_invalid", "No se puede verificar el registro ciego.", 503) from exc
            items.append({
                "id": validation["id"], "name": validation["name"], "status": validation["status"],
                "unlock_date": unlock.isoformat(), "n_periods": len(periods),
                "next_rebalance_due": due.isoformat(), "days_to_unlock": max(0, (unlock - current).days),
                "integrity": integrity,
                "revealed": validation["status"] == "broken_early" or current >= unlock,
            })
        return {"items": items}
