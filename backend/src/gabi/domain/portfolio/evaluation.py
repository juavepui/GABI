"""Saved ranking returns from explicit prices, dates and histories."""
from datetime import date

import pandas as pd


def progress_for(symbols: list[str], as_of_date: str, *, data_as_of, prices: dict, today: date, cost_bps: float = 0) -> dict:
    """Progress from explicit start/end prices and the cache watermark."""
    start = pd.Timestamp(as_of_date)
    now = pd.Timestamp(today)

    # "Obsoleto" = el caché de precios no llega a ningún día DESPUÉS de la
    # fecha guardada todavía — no hay literalmente ningún dato nuevo que
    # comparar, así que un 0.0% aquí no significaría "sin cambios", sino
    # "no hay datos más recientes" — hay que distinguir los dos casos.
    stale = data_as_of is None or data_as_of.normalize() <= start.normalize()

    detail_rows = []
    for symbol in symbols:
        p0 = prices.get((symbol, "start"))
        p1 = prices.get((symbol, "end"))
        ret = (p1 / p0 - 1 - 2 * cost_bps / 10000) if p0 and p1 else None
        detail_rows.append({"symbol": symbol, "price_start": p0, "price_now": p1, "return": ret})
    detail = pd.DataFrame(detail_rows)

    valid_returns = detail["return"].dropna()
    portfolio_return = float(valid_returns.mean()) if not valid_returns.empty else None
    b0 = prices.get(("SPY", "start"))
    b1 = prices.get(("SPY", "end"))
    benchmark_return = (b1 / b0 - 1 - 2 * cost_bps / 10000) if b0 and b1 else None

    return {
        "as_of_date": as_of_date, "today": now.date().isoformat(),
        "data_as_of": data_as_of.date().isoformat() if data_as_of is not None else None,
        "stale": stale,
        "detail": detail, "available": int(valid_returns.shape[0]), "requested": len(symbols),
        "portfolio_return": portfolio_return, "benchmark_return": benchmark_return,
        "excess_return": (portfolio_return - benchmark_return)
        if portfolio_return is not None and benchmark_return is not None else None,
        "missing": sorted(set(symbols) - set(detail.loc[detail["return"].notna(), "symbol"])),
    }


def price_curve_for(symbols: list[str], as_of_date: str, histories: dict) -> pd.DataFrame:
    """`snapshot_price_curve` for given candidates and already read histories (SPY included)."""
    start = pd.Timestamp(as_of_date) - pd.Timedelta(days=7)
    series = {}
    for symbol in symbols:
        h = histories.get(symbol)
        if h is None or h.empty or "adj_close" not in h:
            continue
        s = h["adj_close"].dropna()
        s = s[s.index >= start]
        if not s.empty:
            series[symbol] = s / s.iloc[0] * 100

    if not series:
        return pd.DataFrame()
    basket = pd.concat(series, axis=1).mean(axis=1, skipna=True)

    spy_h = histories.get("SPY")
    spy = pd.Series(dtype=float)
    if spy_h is not None and not spy_h.empty and "adj_close" in spy_h:
        spy = spy_h["adj_close"].dropna()
        spy = spy[spy.index >= start]
        if not spy.empty:
            spy = spy / spy.iloc[0] * 100

    curve = pd.DataFrame({"Cartera": basket})
    if not spy.empty:
        curve["SPY"] = spy
    return curve.dropna(how="all")


def evaluate(symbols: list[str], as_of_date: str, months: int = 6, cost_bps: float = 0, *,
             prices: dict, today: date) -> dict:
    """Rentabilidad total con el mismo peso por candidata, incluyendo el coste de ida y vuelta; los datos que faltan nunca cuentan como cero.

    Precios ya leídos y fecha de corte explícita; sin acceso a cachés ni reloj."""
    start = pd.Timestamp(as_of_date)
    end = start + pd.DateOffset(months=months)
    if end > pd.Timestamp(today):
        return {"status": "pending", "end_date": end.date().isoformat()}
    returns = {}
    for symbol in dict.fromkeys(symbols):
        p0 = prices.get((symbol, "start"))
        p1 = prices.get((symbol, "end"))
        if p0 and p1:
            returns[symbol] = p1 / p0 - 1 - 2 * cost_bps / 10000
    b0 = prices.get(("SPY", "start"))
    b1 = prices.get(("SPY", "end"))
    benchmark = b1 / b0 - 1 - 2 * cost_bps / 10000 if b0 and b1 else None
    portfolio = sum(returns.values()) / len(returns) if returns else None
    return {
        "status": "complete" if len(returns) == len(set(symbols)) and benchmark is not None else "incomplete",
        "end_date": end.date().isoformat(), "available": len(returns), "requested": len(set(symbols)),
        "portfolio_return": portfolio, "benchmark_return": benchmark,
        "excess_return": portfolio - benchmark if portfolio is not None and benchmark is not None else None,
        "missing": sorted(set(symbols) - returns.keys()),
    }
