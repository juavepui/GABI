"""Home notices: blind rebalances due within a week, the #44 analysis and whether the daily follow-up runs (#290)."""

from collections.abc import Callable
from datetime import date
from typing import Protocol

from gabi.application.administration.periodic import SOON_DAYS
from gabi.application.errors import QueryError
from gabi.domain.administration import periodic_health

LastDecisions = Callable[[], tuple[dict | None, dict | None]]


class BlindList(Protocol):
    def list_status(self) -> dict: ...


class SmallmidState(Protocol):
    def state(self, today: date) -> dict: ...


class Notices:
    def __init__(self, blind: BlindList, smallmid: SmallmidState, today: Callable[[], date],
                 last_decisions: LastDecisions | None = None):
        self.blind, self.smallmid, self.today = blind, smallmid, today
        self.last_decisions = last_decisions

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
        periodic = None
        if self.last_decisions is not None:
            try:
                periodic = periodic_health.assess(*self.last_decisions(), current)
            except OSError:
                periodic = None
        return {"blind_rebalances": rebalances, "blind_available": blind_available, "smallmid": smallmid,
                "periodic": periodic}
