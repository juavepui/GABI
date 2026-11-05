"""Semáforo del mercado (#308): read-only, from prices and FRED data already stored; never downloads.

The result is kept in memory until the database or the universe file changes, so opening Inicio again does
not reread the price window.
"""

import threading
from collections.abc import Callable
from datetime import date, timedelta
from typing import Protocol

import pandas as pd

from gabi.domain.market import market_health as rules

# 200 sessions for the long average plus the sessions counted for «días en el estado», in calendar days.
WINDOW_DAYS = 560
VIX_SERIES = "VIXCLS"


class MarketHealthSource(Protocol):
    def stamp(self) -> tuple: ...
    def universe(self) -> list[str]: ...
    def prices_since(self, symbols: list[str], start: str) -> pd.DataFrame: ...
    def series_since(self, series_id: str, start: str) -> pd.Series: ...


class MarketHealthQueries:
    def __init__(self, source: MarketHealthSource, benchmark: Callable[[], str], today: Callable[[], date]):
        self.source, self.benchmark, self.today = source, benchmark, today
        self._lock = threading.Lock()
        self._cached: tuple[tuple, dict] | None = None  # (key, result)

    def _key(self) -> tuple:
        return self.source.stamp(), self.benchmark(), self.today()

    def cached(self) -> dict | None:
        """The result only when it is already computed for the current data; never reads prices."""
        key = self._key()
        with self._lock:
            return self._cached[1] if self._cached is not None and self._cached[0] == key else None

    def current(self) -> dict:
        key = self._key()
        with self._lock:
            if self._cached is not None and self._cached[0] == key:
                return self._cached[1]
        result = self._compute(key[1], key[2])
        with self._lock:
            self._cached = (key, result)
        return result

    def _compute(self, benchmark: str, today: date) -> dict:
        start = (today - timedelta(days=WINDOW_DAYS)).isoformat()
        universe = [symbol for symbol in dict.fromkeys(self.source.universe()) if symbol != benchmark]
        frame = self.source.prices_since([benchmark, *universe], start)
        index = frame[frame["symbol"] == benchmark].set_index("date").drop(columns="symbol")
        companies = frame[frame["symbol"] != benchmark]
        closes = pd.DataFrame()
        if not companies.empty:
            # Per company, adjusted closes only when all of them are there: never a mix in one series.
            complete = companies["adj_close"].notna().groupby(companies["symbol"]).transform("all")
            price = companies["adj_close"].where(complete, companies["close"])
            closes = companies.assign(price=price).pivot(index="date", columns="symbol", values="price").sort_index()
        vix = self.source.series_since(VIX_SERIES, start)
        result = rules.evaluate(index, closes, vix)
        return result | {"benchmark": benchmark, "universe_count": len(universe), "affects_score": False}
