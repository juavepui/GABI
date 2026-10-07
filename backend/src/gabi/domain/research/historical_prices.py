"""Original archive price validation; no persistence or identity attribution."""

import numpy as np
import pandas as pd


def prepare_price_chunk(frame: pd.DataFrame, symbols: set[str], start: str, end: str) -> tuple[pd.DataFrame, int]:
    frame = frame.rename(columns={"adjusted_close": "adj_close"}).copy()
    frame["symbol"] = frame["symbol"].str.replace(".", "-", regex=False)
    frame = frame[(frame["date"] >= start) & (frame["date"] < end) & frame["symbol"].isin(symbols)]
    pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="raise")
    columns = ["open", "high", "low", "close", "adj_close", "volume"]
    values = frame[columns].apply(pd.to_numeric, errors="coerce")
    valid = np.isfinite(values).all(axis=1) & (values[columns[:-1]] > 0).all(axis=1) & (values["volume"] >= 0)
    valid &= values["high"] + 0.001 >= values[["open", "close", "low"]].max(axis=1)
    valid &= values["low"] - 0.001 <= values[["open", "close", "high"]].min(axis=1)
    rejected = int((~valid).sum())
    frame[columns] = values
    frame = frame[valid]
    if frame.duplicated(["symbol", "date"]).any():
        raise ValueError("Duplicate price observations within source chunk")
    return frame, rejected
