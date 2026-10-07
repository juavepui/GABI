"""Whether the cached prices include the last closed market session."""

from collections.abc import Iterable, Mapping
from datetime import date, datetime

import exchange_calendars as xcals
import pandas as pd

MAX_BEHIND_SHARE = 0.05  # current-universe tolerance before a blind rebalance
MAINTENANCE_BENCHMARKS = ("SPY", "RSP")


def maintenance_freshness(symbols: list[str], prices: Mapping[str, str | None], session: str) -> tuple[dict, float, bool]:
    """Exact benchmark closes and no more than 5% of the current universe behind."""
    behind = sum((prices.get(symbol) or "") < session for symbol in symbols) / len(symbols) if symbols else 1.0
    benchmarks = {symbol: prices.get(symbol) for symbol in MAINTENANCE_BENCHMARKS}
    fresh = all(value == session for value in benchmarks.values()) and behind <= MAX_BEHIND_SHARE
    return benchmarks, behind, fresh


def last_completed_session(now: datetime) -> date:
    """The last NYSE session whose close is before `now` (an aware datetime)."""
    calendar = xcals.get_calendar("XNYS")
    session = calendar.date_to_session(now.date().isoformat(), direction="previous")
    if calendar.session_close(session) > pd.Timestamp(now):
        session = calendar.previous_session(session)
    return session.date()


def prices_current(price_dates: Iterable[date | None], session: date,
                   max_behind_share: float = MAX_BEHIND_SHARE) -> bool:
    """At most `max_behind_share` of the symbols lack the close of `session`; a missing price counts as behind."""
    dates = list(price_dates)
    if not dates:
        return False
    behind = sum(value is None or value < session for value in dates)
    return behind / len(dates) <= max_behind_share
