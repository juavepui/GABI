"""Incremental Yahoo price rules: what to skip, the overlap window, response validation and adjustment changes."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

COLS = {"Open": "open", "High": "high", "Low": "low", "Close": "close",
        "Adj Close": "adj_close", "Volume": "volume"}
OVERLAP_DAYS = 14


def yahoo_symbol(symbol: str) -> str:
    """Yahoo Finance uses '-' instead of '.' (BRK.B -> BRK-B)."""
    return symbol.replace(".", "-")


def already_checked(latest: str | None, session: str, checkpoint: dict, *, force: bool, full_refresh: bool,
                    due: bool) -> bool:
    if force or full_refresh or not latest or due:
        return False
    return latest >= session or checkpoint.get("checked_session") == session


def overlap_start(latest: str | None) -> str | None:
    return (pd.Timestamp(latest) - timedelta(days=OVERLAP_DAYS)).date().isoformat() if latest else None


def download_params(from_date: str | None, full: bool, end: str) -> dict:
    return {"start": from_date, "end": end} if from_date else {"period": "max" if full else "2y"}


def ticker_frame(data: object, symbol: str) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame):
        raise ValueError("Yahoo no devolvió una tabla de precios.")
    if isinstance(data.columns, pd.MultiIndex):
        ticker = yahoo_symbol(symbol)
        data = data[ticker] if ticker in data.columns.get_level_values(0) else data.xs(ticker, level=1, axis=1)
    return data


def clean_prices(data: pd.DataFrame, session: str) -> pd.DataFrame:
    """Completed sessions only, every price positive and consistent, no duplicates; otherwise reject the window."""
    data = data.reindex(columns=list(COLS)).copy()
    data.index = pd.to_datetime(data.index).tz_localize(None).normalize()
    data = data.loc[data.index <= pd.Timestamp(session)]
    valid = np.isfinite(data).all(axis=1) & (data[["Open", "High", "Low", "Close", "Adj Close"]] > 0).all(axis=1)
    valid &= (data.Volume >= 0) & (data.High >= data[["Open", "Close", "Low"]].max(axis=1))
    valid &= data.Low <= data[["Open", "Close", "High"]].min(axis=1)
    if data.empty or not valid.all() or data.index.has_duplicates:
        raise ValueError("Respuesta de precios vacía, duplicada o con observaciones inválidas.")
    return data.sort_index()


def adjustment_changed(old: pd.DataFrame, incoming: pd.DataFrame) -> bool:
    """Dividend/split adjustment or close basis changed on overlapping sessions."""
    overlap = old.index.intersection(incoming.index)
    if not len(overlap):
        return False
    old_adjust = old.loc[overlap, "adj_close"] / old.loc[overlap, "close"]
    new_adjust = incoming.loc[overlap, "adj_close"] / incoming.loc[overlap, "close"]
    changed = bool((~np.isclose(old_adjust, new_adjust, rtol=1e-6, atol=1e-8)).any())
    ratio = incoming.loc[overlap, "close"] / old.loc[overlap, "close"]
    return changed or bool(len(ratio) >= 2 and not np.isclose(ratio.median(), 1, rtol=1e-5))


def first_session_missing(data: pd.DataFrame, first: str | None) -> bool:
    return bool(first) and data.index.min().date().isoformat() > first


def end_date(now: datetime) -> str:
    return (now.date() + timedelta(days=1)).isoformat()
