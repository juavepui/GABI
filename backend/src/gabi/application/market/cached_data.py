"""Local price/fundamental cache queries over a specific read port; no downloads or schema writes."""

import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Protocol

import pandas as pd

PRICE_COLUMNS = ["date", "open", "high", "low", "close", "volume", "adj_close"]
ERROR_COLUMNS = ["source", "symbol", "reason", "occurred_at"]


class CacheReader(Protocol):
    def prices(self, symbol: str) -> list[tuple]: ...
    def prices_multi(self, symbols: list[str]) -> list[tuple]: ...
    def price_coverage(self, symbols: list[str]) -> list[tuple]: ...
    def last_price(self, symbol: str, as_of: str) -> tuple | None: ...
    def latest_adjusted(self, symbols: list[str]) -> dict[str, tuple]: ...
    def prices_from(self, symbol: str, start: str) -> list[tuple]: ...
    def split_ratios_after(self, symbol: str, as_of: str) -> list[float]: ...
    def fundamentals(self, symbols: list[str]) -> list[tuple]: ...
    def fundamentals_fetched_at(self, symbols: list[str]) -> list[tuple]: ...
    def update_errors(self, since: str, source: str | None = None) -> list[tuple]: ...


def parse_fetched_at(rows: Iterable[tuple]) -> dict[str, datetime | None]:
    result: dict[str, datetime | None] = {}
    for symbol, stamp in rows:
        try:
            result[symbol] = datetime.fromisoformat(stamp)  # non-str stamps fall back to None, as before
        except (TypeError, ValueError):
            result[symbol] = None
    return result


def _frame(rows: list[tuple], columns: list[str]) -> pd.DataFrame:
    # Same record conversion as pandas.read_sql_query, which the facade used before.
    return pd.DataFrame.from_records(rows, columns=columns, coerce_float=True)


def prices(reader: CacheReader, symbol: str) -> pd.DataFrame:
    frame = _frame(reader.prices(symbol), PRICE_COLUMNS)
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")


def prices_multi(reader: CacheReader, symbols: list[str]) -> dict[str, pd.DataFrame]:
    if not symbols:
        return {}
    frame = _frame(reader.prices_multi(symbols), ["symbol", *PRICE_COLUMNS])
    if frame.empty:
        return {}
    frame["date"] = pd.to_datetime(frame["date"])
    return {symbol: group.drop(columns=["symbol"]).set_index("date") for symbol, group in frame.groupby("symbol")}


def price_coverage(reader: CacheReader, symbols: list[str]) -> dict[str, dict]:
    if not symbols:
        return {}
    return {symbol: {"adjusted_count": count, "latest_adjusted_date": latest}
            for symbol, count, latest in reader.price_coverage(symbols)}


def latest_adjusted(reader: CacheReader, symbols: list[str]) -> dict[str, tuple]:
    return reader.latest_adjusted(symbols) if symbols else {}


def price_as_of(reader: CacheReader, symbol: str, as_of: str) -> float | None:
    row = reader.last_price(symbol, as_of)
    return float(row[0]) if row and row[0] is not None else None


def has_verified_price_as_of(reader: CacheReader, symbol: str, as_of: str) -> bool:
    row = reader.last_price(symbol, as_of)
    return bool(row and row[1] is not None)


def split_factor_since(reader: CacheReader, symbol: str, as_of: str) -> float:
    factor = 1.0
    for ratio in reader.split_ratios_after(symbol, as_of):
        if ratio:
            factor *= ratio
    return factor


def fundamentals(reader: CacheReader, symbols: list[str]) -> dict[str, dict]:
    if not symbols:
        return {}
    return {symbol: {"fetched_at": fetched_at, "info": json.loads(info), "quarterly_income": json.loads(income),
                     "quarterly_cashflow": json.loads(cashflow)}
            for symbol, fetched_at, info, income, cashflow in reader.fundamentals(symbols)}


def fundamentals_fetched_at(reader: CacheReader, symbols: list[str]) -> dict[str, datetime | None]:
    return parse_fetched_at(reader.fundamentals_fetched_at(symbols)) if symbols else {}


def recent_update_errors(reader: CacheReader, *, now: datetime, source: str | None = None,
                         since_hours: float = 24 * 7) -> pd.DataFrame:
    return _frame(reader.update_errors((now - timedelta(hours=since_hours)).isoformat(), source), ERROR_COLUMNS)


WINDOW_COLUMNS = ["date", "open", "high", "low", "close", "adj_close", "volume"]


def prices_from(reader: CacheReader, symbol: str, start: str) -> pd.DataFrame:
    """Cached rows from ``start``, indexed by date, in the column order the price sync compares."""
    frame = _frame(reader.prices_from(symbol, start), WINDOW_COLUMNS)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")
