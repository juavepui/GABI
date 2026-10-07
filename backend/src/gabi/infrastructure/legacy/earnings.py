"""Explicit Yahoo earnings download; legacy compatibility supplies only error wording."""
import concurrent.futures as cf
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from gabi.application.market.earnings_sync import EarningsAttempt
from gabi.application.market.earnings_sync import sync_earnings_surprises as run_sync
from gabi.infrastructure.storage.earnings import SqliteEarnings


class YahooEarnings:
    @staticmethod
    def fetch(symbol: str) -> pd.DataFrame:
        from gabi.data_fetch import normalize_symbol

        table = yf.Ticker(normalize_symbol(symbol)).earnings_dates
        return table if table is not None else pd.DataFrame()

    def attempts(self, symbols: list[str], max_workers: int):
        with cf.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetch, symbol): symbol for symbol in symbols}
            for future in cf.as_completed(futures):
                symbol = futures[future]
                try:
                    yield EarningsAttempt(symbol, table=future.result())
                except Exception as exc:
                    yield EarningsAttempt(symbol, error=exc)


def classify_error(exc: Exception) -> str:
    from gabi.data_fetch import _classify_error

    return _classify_error(exc, service="Yahoo Finance")[1]


def sync_earnings_surprises(data_dir: Path, symbols: list[str], *, today: date | None = None,
                           now: datetime | None = None, max_workers: int = 6, progress_cb=None) -> dict:
    return run_sync(symbols, YahooEarnings(), SqliteEarnings(data_dir, now=lambda: now or datetime.now(UTC)), classify_error,
                    today=today or date.today(), max_workers=max_workers, progress_cb=progress_cb)
