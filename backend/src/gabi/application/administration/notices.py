"""Home notices of the old Streamlit portada: blind rebalances due within a week and the #44 analysis."""

from collections.abc import Callable
from datetime import date
from typing import Protocol

from gabi.application.errors import QueryError

SOON_DAYS = 7  # periodic_tasks.SOON_DAYS


class BlindList(Protocol):
    def list_status(self) -> dict: ...


class SmallmidState(Protocol):
    def state(self, today: date) -> dict: ...


class Notices:
    def __init__(self, blind: BlindList, smallmid: SmallmidState, today: Callable[[], date]):
        self.blind, self.smallmid, self.today = blind, smallmid, today

    def current(self) -> dict:
        """Like the old portada, a failing source hides its notice instead of breaking the page."""
        current = self.today()
        rebalances, blind_available = [], True
        try:
            for item in self.blind.list_status()["items"]:
                days = (date.fromisoformat(item["next_rebalance_due"]) - current).days
                if item["status"] == "locked" and days <= SOON_DAYS:
                    rebalances.append({"id": item["id"], "name": item["name"], "due": item["next_rebalance_due"],
                                       "days": days, "overdue": days <= 0})
        except QueryError:
            blind_available = False
        try:
            smallmid = self.smallmid.state(current)
        except OSError:
            smallmid = None
        return {"blind_rebalances": rebalances, "blind_available": blind_available, "smallmid": smallmid}
