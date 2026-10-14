"""Rules over Yahoo downloads and the local market cache; no I/O."""

from collections.abc import Mapping
from datetime import date, datetime

import pandas as pd

NO_PRICES = "Sin datos de precio devueltos por Yahoo Finance (posible ticker incorrecto o deslistado)"
NO_FUNDAMENTALS = "Yahoo Finance no devolvió datos fundamentales para este ticker"
FUNDAMENTAL_SIGNALS = ("regularMarketPrice", "currentPrice", "sector", "marketCap")
DECISION_CLOSES = 126
DECISION_MAX_AGE_DAYS = 7


def ticker_frame(data: pd.DataFrame, ticker: str, n_tickers: int) -> pd.DataFrame | None:
    """One ticker's rows of a batch download, whichever column level holds the ticker."""
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if ticker in data.columns.get_level_values(0):
                return data[ticker]
            if ticker in data.columns.get_level_values(1):
                return data.xs(ticker, level=1, axis=1)
            return None
        return data if n_tickers == 1 else None
    except Exception:
        return None


def split_ratios(splits: pd.Series | None) -> dict[str, float]:
    if splits is None or splits.empty:
        return {}
    return {d.strftime("%Y-%m-%d"): float(r) for d, r in splits.items()}


def fundamentals_info(info: Mapping | None, keys) -> dict:
    """The configured info keys, or ValueError when Yahoo returned no usable signal."""
    info = info or {}
    if not any(info.get(k) is not None for k in FUNDAMENTAL_SIGNALS):
        raise ValueError(NO_FUNDAMENTALS)
    return {k: info.get(k) for k in keys}


def adjusted_on_or_before(history: pd.DataFrame, as_of_date: str) -> bool:
    return not history.empty and history.loc[history.index <= pd.Timestamp(as_of_date), "adj_close"].notna().any()


def decision_ready(item: Mapping, today: date) -> bool:
    """At least 126 adjusted closes, the latest at most a week old."""
    latest = item.get("latest_adjusted_date")
    return (item.get("adjusted_count", 0) >= DECISION_CLOSES and latest is not None
            and (today - datetime.fromisoformat(latest).date()).days <= DECISION_MAX_AGE_DAYS)


def fundamentals_status(digest: str, previous: Mapping | None, fingerprint) -> str:
    """new / unchanged / revised against the cached snapshot (its fetch time excluded)."""
    if not previous:
        return "new"
    return "unchanged" if digest == fingerprint({k: v for k, v in previous.items() if k != "fetched_at"}) else "revised"


def stale_fundamentals(symbols: list[str], fetched_at: Mapping, failed: set[str], now: datetime,
                       max_age_hours: float, *, refresh_all: bool) -> list[str]:
    """Symbols whose fundamentals are missing, failed last time or older than the threshold."""
    return [s for s in symbols
            if refresh_all or s in failed or fetched_at.get(s) is None
            or (now - fetched_at[s]).total_seconds() > max_age_hours * 3600]


def universe_failures(price_failed: Mapping, fundamentals_failed: Mapping, benchmark: str) -> dict[str, dict]:
    """Per company: why its price or fundamentals failed; the internal benchmark is not a company."""
    failed: dict[str, dict] = {}
    for symbol, reason in price_failed.items():
        if symbol != benchmark:
            failed.setdefault(symbol, {})["precio"] = reason
    for symbol, reason in fundamentals_failed.items():
        failed.setdefault(symbol, {})["fundamentales"] = reason
    return failed
