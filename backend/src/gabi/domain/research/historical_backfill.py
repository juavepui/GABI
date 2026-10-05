"""Rules of the free 1996-2015 backfill that do not depend on a source or the database."""
import pandas as pd


def overlaps_membership(prices: pd.DatetimeIndex, history: pd.DataFrame, symbol: str, end: str) -> bool:
    """Whether provider prices fall inside any dated index membership interval of ``symbol`` before ``end``."""
    history = history[history["date"] < end].sort_values("date")
    dates = history["date"].tolist() + [end]
    present = [symbol in {s.replace(".", "-") for s in tickers.split(",")} for tickers in history["tickers"]]
    first = None
    for i, member in enumerate(present + [False]):
        if member and first is None:
            first = dates[i]
        if not member and first is not None:
            if ((prices >= pd.Timestamp(first)) & (prices < pd.Timestamp(dates[i]))).any():
                return True
            first = None
    return False
