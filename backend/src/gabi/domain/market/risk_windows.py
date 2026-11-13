"""Windows and dates of the price-risk figures the company page and Comparar show (#175).

The ranking's volatility and maximum drawdown use the whole cached history. This module states that
window and, for the drawdown, its peak and trough; the 5- and 3-year drawdowns are informative only and
never enter the score. Same price basis as `risk.compute_risk_metrics`: adjusted closes when every
session has one, plain closes otherwise.
"""

import pandas as pd

WINDOWS = (("full", None), ("5y", 5), ("3y", 3))


def price_basis(frame: pd.DataFrame) -> tuple[pd.Series, str]:
    """Dated closes on the same basis as the ranking's risk metrics."""
    column = "adj_close" if "adj_close" in frame and frame["adj_close"].notna().all() else "close"
    series = pd.Series(frame[column].to_numpy(dtype=float), index=pd.to_datetime(frame["date"])).dropna()
    return series.sort_index(), column


def drawdown(series: pd.Series) -> dict:
    """Largest fall from a running peak to a later trough, with both dates; None without prices."""
    if series.empty:
        return {"value": None, "peak_date": None, "trough_date": None, "start": None}
    falls = series / series.cummax() - 1
    trough = falls.idxmin()
    peak = series.loc[:trough].idxmax()
    return {"value": float(falls.min()), "peak_date": peak.date().isoformat(),
            "trough_date": trough.date().isoformat(), "start": series.index[0].date().isoformat()}


def risk_windows(frame: pd.DataFrame) -> dict:
    """History span, the drawdown of the whole history and of the last 5 and 3 years."""
    if frame is None or frame.empty or "close" not in frame:
        empty = drawdown(pd.Series(dtype=float))
        return {"history_start": None, "history_end": None, "sessions": 0, "price_basis": None,
                "drawdowns": [{"window": window, "complete": False, **empty} for window, _ in WINDOWS]}
    series, column = price_basis(frame)
    end = series.index[-1] if not series.empty else None
    rows = []
    for window, years in WINDOWS:
        part = series if years is None or end is None else series[series.index > end - pd.DateOffset(years=years)]
        # A window longer than the history is the whole history, not a shorter fake one.
        covered = years is None or (not series.empty and series.index[0] <= end - pd.DateOffset(years=years))
        rows.append({"window": window, "complete": bool(covered), **drawdown(part)})
    return {"history_start": None if series.empty else series.index[0].date().isoformat(),
            "history_end": None if end is None else end.date().isoformat(), "sessions": int(len(series)),
            "price_basis": column, "drawdowns": rows}
