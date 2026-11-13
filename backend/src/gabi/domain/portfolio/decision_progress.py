"""Progress of a saved weighted decision plan from cached adjusted closes."""

from datetime import date
from typing import Any

import pandas as pd


def _adjusted_at(history: pd.DataFrame, target: pd.Timestamp) -> float | None:
    if history.empty or "adj_close" not in history:
        return None
    values = history["adj_close"].dropna()
    values = values[(values.index <= target) & (values.index >= target - pd.Timedelta(days=7))]
    return float(values.iloc[-1]) if not values.empty else None


def progress(created_at: str, decisions: list[dict], histories: dict[str, pd.DataFrame],
             today: date, cost_bps: float = 0) -> dict:
    """Preserve the legacy 7-day price tolerance, weight renormalization and SPY baseline."""
    as_of = created_at[:10]
    positions = [row for row in decisions if float(row.get("target_pct", 0)) > 0]
    if not positions:
        return {"as_of_date": as_of, "created_at": created_at, "today": today.isoformat(),
                "data_as_of": None, "stale": False, "detail": [], "available": 0,
                "requested": 0, "portfolio_return": None, "benchmark_return": None,
                "excess_return": None, "missing": [], "curve": []}
    symbols = [str(row["symbol"]) for row in positions]
    start, end = pd.Timestamp(as_of), pd.Timestamp(today)
    latest = max((history["adj_close"].dropna().index.max() for history in histories.values()
                  if not history.empty and "adj_close" in history and not history["adj_close"].dropna().empty),
                 default=None)
    stale = latest is None or latest.normalize() <= start.normalize()
    detail: list[dict[str, Any]] = []
    for row in positions:
        symbol, weight = str(row["symbol"]), float(row["target_pct"])
        history = histories.get(symbol, pd.DataFrame())
        first, last = _adjusted_at(history, start), _adjusted_at(history, end)
        result = (last / first - 1 - 2 * cost_bps / 10000) if first and last else None
        detail.append({"symbol": symbol, "weight_pct": weight, "price_start": first,
                       "price_now": last, "return": float(result) if result is not None else None})
    valid = [row for row in detail if row["return"] is not None]
    total_weight = sum(float(row["weight_pct"]) for row in valid)
    portfolio_return = (sum(float(row["return"]) * float(row["weight_pct"]) for row in valid) / total_weight
                        if total_weight > 0 else None)
    spy = histories.get("SPY", pd.DataFrame())
    b0, b1 = _adjusted_at(spy, start), _adjusted_at(spy, end)
    benchmark_return = (b1 / b0 - 1 - 2 * cost_bps / 10000) if b0 and b1 else None
    curve: list[dict] = []
    if positions:
        series = {}
        for row in positions:
            symbol = str(row["symbol"])
            history = histories.get(symbol, pd.DataFrame())
            if history.empty or "adj_close" not in history:
                continue
            values = history["adj_close"].dropna()
            values = values[values.index >= start - pd.Timedelta(days=7)]
            if not values.empty:
                series[symbol] = values / values.iloc[0] * 100
        if series:
            aligned = pd.concat(series, axis=1).ffill()
            weights = pd.Series({symbol: float(next(row["target_pct"] for row in positions
                                                    if row["symbol"] == symbol)) for symbol in aligned.columns})
            basket = aligned.mul(weights, axis=1).sum(axis=1) / weights.sum()
            frame = pd.DataFrame({"portfolio": basket})
            if not spy.empty and "adj_close" in spy:
                spy_values = spy["adj_close"].dropna()
                spy_values = spy_values[spy_values.index >= start - pd.Timedelta(days=7)]
                if not spy_values.empty:
                    frame["spy"] = spy_values / spy_values.iloc[0] * 100
            for day, row in frame.dropna(how="all").tail(500).iterrows():
                curve.append({"date": day.date().isoformat(),
                              "portfolio": float(row["portfolio"]) if pd.notna(row["portfolio"]) else None,
                              "spy": float(row["spy"]) if "spy" in row and pd.notna(row["spy"]) else None})
    return {"as_of_date": as_of, "created_at": created_at, "today": today.isoformat(),
            "data_as_of": latest.date().isoformat() if latest is not None else None, "stale": stale,
            "detail": detail, "available": len(valid), "requested": len(positions),
            "portfolio_return": portfolio_return, "benchmark_return": benchmark_return,
            "excess_return": portfolio_return - benchmark_return if portfolio_return is not None
            and benchmark_return is not None else None,
            "missing": sorted(set(symbols) - {row["symbol"] for row in valid}), "curve": curve}
