"""Explicit reported-EPS sync: one source attempt, cached reaction prices and a write per symbol."""
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd

from gabi.domain.market.events import compute_price_reaction, parse_earnings_history


@dataclass(frozen=True)
class EarningsAttempt:
    symbol: str
    table: pd.DataFrame | None = None
    error: Exception | None = None


class EarningsSource(Protocol):
    def attempts(self, symbols: list[str], max_workers: int) -> Iterable[EarningsAttempt]: ...


class EarningsStore(Protocol):
    def reaction_prices(self, symbol: str, dates: list[date]) -> pd.DataFrame: ...
    def save(self, rows: list[dict]) -> None: ...


def sync_earnings_surprises(symbols: list[str], source: EarningsSource, store: EarningsStore,
                           classify_error: Callable[[Exception], str], *, today: date, max_workers: int = 6,
                           progress_cb: Callable[[int, int], None] | None = None) -> dict:
    failed: dict[str, str] = {}
    if not symbols:
        return failed
    for done, outcome in enumerate(source.attempts(symbols, max_workers), 1):
        try:
            if outcome.error is not None:
                raise outcome.error
            rows = parse_earnings_history(outcome.symbol, outcome.table, today=today)
            if rows:
                prices = store.reaction_prices(outcome.symbol, [row["earnings_date"] for row in rows])
                for row in rows:
                    row["price_reaction_pct"] = compute_price_reaction(prices, row["earnings_date"])
                store.save(rows)
        except Exception as exc:
            failed[outcome.symbol] = classify_error(exc)
        if progress_cb:
            progress_cb(done, len(symbols))
    return failed
