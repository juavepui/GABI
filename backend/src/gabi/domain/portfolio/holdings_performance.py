"""Daily evolution, returns, risk and attribution of the real portfolio (#294).

The value of each session is the shares held × that session's cached close × that
session's cached rate. A session where a held symbol has no close or rate is a gap:
it is listed with the symbols missing and skipped, never filled; its flows enter on the
next complete session. Flows are external money: a purchase brings its cost with
commission (+), a sale takes out what it raised (−) and a dividend takes out its net
amount (−), each converted with the rate the broker applied or the cached rate of its date.

The formulas are shared: the unitised NAV and the money-weighted return come from
``contributions`` (#244) and the daily returns from ``metrics``. The benchmark is SPY's
adjusted close (dividends reinvested) in euros, bought and sold with the same euros on
the same sessions.
"""

import math
from datetime import date

import pandas as pd

from gabi.domain.portfolio import contributions, metrics
from gabi.domain.portfolio.holdings import EPSILON, kind

VERSION = "holdings-performance-v2"
LOOKBACK_DAYS = 7
SIGN = {"buy": 1, "sell": -1, "dividend": -1}


def _at_or_before(series: pd.Series | None, day: pd.Timestamp) -> float | None:
    if series is None or series.empty:
        return None
    recent = series[(series.index <= day) & (series.index >= day - pd.Timedelta(days=LOOKBACK_DAYS))].dropna()
    return float(recent.iloc[-1]) if not recent.empty else None


def _rate(lot: dict, euros_per_unit: dict[str, pd.Series], day: pd.Timestamp) -> float | None:
    if lot["currency"] == "EUR":
        return 1.0
    return lot.get("fx_rate") or _at_or_before(euros_per_unit.get(lot["currency"]), day)


def movement_eur(lot: dict, rate: float) -> float:
    """Euros the movement brings in (+) or takes out (−) of the portfolio."""
    movement = kind(lot)
    if movement == "buy":
        return (lot["shares"] * lot["price"] + lot["commission"]) * rate
    if movement == "sell":
        return -(lot["shares"] * lot["price"] - lot["commission"]) * rate
    return -(lot["price"] - (lot.get("withholding") or 0.0)) * rate


def history(lots: list[dict], closes: dict[str, pd.Series], euros_per_unit: dict[str, pd.Series],
            sessions: pd.DatetimeIndex) -> dict:
    """Daily EUR value and flows over ``sessions`` from the first movement; gaps listed, never filled.

    A movement without a rate (and a non-EUR movement on a currency without rates) blocks the series:
    its euros are unknown, so no return can be computed honestly."""
    lots = sorted(lots, key=lambda row: (row["purchase_date"], row.get("id") or 0))
    sessions = sessions.sort_values()
    if not lots:
        return {"status": "no_movements"}
    first = pd.Timestamp(lots[0]["purchase_date"])
    sessions = sessions[sessions >= first]
    blocked, flows = [], []
    for lot in lots:
        day = pd.Timestamp(lot["purchase_date"])
        later = sessions[sessions >= day]
        rate = _rate(lot, euros_per_unit, day)
        if rate is None or later.empty:
            blocked.append({"id": lot.get("id"), "symbol": lot["symbol"], "date": lot["purchase_date"],
                            "kind": kind(lot), "reason": "missing_fx" if rate is None else "after_last_session"})
            continue
        flows.append((later[0], lot, movement_eur(lot, rate)))
    if blocked:
        return {"status": "blocked", "blocked": blocked}
    shares: dict[str, float] = {}
    rows, gaps, pending = [], [], 0.0
    queue = list(flows)
    for session in sessions:
        while queue and queue[0][0] <= session:
            _, lot, euros = queue.pop(0)
            pending += euros
            if kind(lot) != "dividend":
                change = lot["shares"] * (1 if kind(lot) == "buy" else -1)
                shares[lot["symbol"]] = shares.get(lot["symbol"], 0.0) + change
        held = {symbol: count for symbol, count in shares.items() if count > EPSILON}
        missing, value, by_symbol = [], 0.0, {}
        for symbol, count in held.items():
            close = closes.get(symbol)
            price = float(close[session]) if close is not None and session in close.index \
                and pd.notna(close[session]) and close[session] > 0 else None
            currency = next(lot["currency"] for _, lot, _ in flows if lot["symbol"] == symbol)
            rates = euros_per_unit.get(currency)
            rate = 1.0 if currency == "EUR" else (float(rates[session]) if rates is not None and session in rates.index
                                                  and pd.notna(rates[session]) and rates[session] > 0 else None)
            if price is None or rate is None:
                missing.append(symbol)
                continue
            by_symbol[symbol] = count * price * rate
            value += by_symbol[symbol]
        if missing:
            gaps.append({"date": session.date().isoformat(), "symbols": sorted(missing)})
            continue
        rows.append({"date": session, "flow_eur": pending, "value_eur": value, **{f"v:{k}": v for k, v in
                                                                                     by_symbol.items()}})
        pending = 0.0
    frame = pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame(columns=["flow_eur", "value_eur"])
    frame["contributed_eur"] = frame["flow_eur"].cumsum() if not frame.empty else []
    return {"status": "ok" if not frame.empty else "no_complete_session", "daily": frame, "gaps": gaps,
            "flows": [(session.date(), euros) for session, _, euros in flows],
            "pending_eur": pending}


def risk(daily: pd.DataFrame) -> dict:
    """TWR, money-weighted return, the largest fall with its dates and the annual volatility."""
    nav = contributions.unitised_nav(daily["value_eur"], daily["flow_eur"])
    drawdown = nav / nav.cummax() - 1
    trough = drawdown.idxmin()
    peak = nav.loc[:trough].idxmax()
    recovered = nav.loc[trough:][nav.loc[trough:] >= nav[peak]]
    returns = metrics.returns_from_nav(nav)
    years = (daily.index[-1] - daily.index[0]).days / 365
    twr = float(nav.iloc[-1] / nav.iloc[0] - 1)
    flows = [(day.date(), float(flow)) for day, flow in daily["flow_eur"].items() if flow]
    return {
        "start": daily.index[0].date().isoformat(), "end": daily.index[-1].date().isoformat(),
        "sessions": len(daily), "final_value_eur": float(daily["value_eur"].iloc[-1]),
        "net_contributed_eur": float(daily["contributed_eur"].iloc[-1]),
        "twr": twr, "twr_annualised": (1 + twr) ** (1 / years) - 1 if years >= 1 else None,
        # Annual rates only with a year of history: over a few days they would be meaningless.
        "money_weighted": contributions.xirr(flows, daily.index[-1].date(), float(daily["value_eur"].iloc[-1]))
        if years >= 1 else None,
        "max_drawdown": float(drawdown.min()),
        "peak_date": peak.date().isoformat() if drawdown.min() < 0 else None,
        "trough_date": trough.date().isoformat() if drawdown.min() < 0 else None,
        "recovered_date": recovered.index[0].date().isoformat() if drawdown.min() < 0 and len(recovered) else None,
        "volatility": float(returns.std() * math.sqrt(metrics.TRADING_DAYS_PER_YEAR)) if len(returns) >= 2 else None,
        "series": [{"date": day.date().isoformat(), "value_eur": float(value), "nav": float(unit)}
                   for (day, value), unit in zip(daily["value_eur"].items(), nav, strict=True)],
    }


def benchmark(daily: pd.DataFrame, spy_adjusted: pd.Series, euros_per_dollar: pd.Series) -> dict:
    """SPY (dividends reinvested) in euros with the same flows on the same complete sessions.

    A withdrawal larger than the SPY held sells it all and records the shortfall, so the flows stay equal."""
    units, rows, shortfall, missing = 0.0, [], 0.0, []
    for day, flow in daily["flow_eur"].items():
        price, rate = spy_adjusted.get(day), euros_per_dollar.get(day)
        if price is None or rate is None or pd.isna(price) or pd.isna(rate) or price <= 0 or rate <= 0:
            missing.append(day.date().isoformat())
            continue
        euro_price = float(price) * float(rate)
        units += flow / euro_price
        if units < 0:
            shortfall += -units * euro_price
            units = 0.0
        rows.append({"date": day, "flow_eur": float(flow), "value_eur": units * euro_price})
    if missing:
        return {"status": "missing_prices", "missing": missing[:20], "missing_sessions": len(missing)}
    frame = pd.DataFrame(rows).set_index("date")
    frame["contributed_eur"] = frame["flow_eur"].cumsum()
    return {"status": "ok", **risk(frame), "shortfall_eur": shortfall}


def attribution(lots: list[dict], final_values: dict[str, float], rates: dict[int, float],
                sectors: dict[str, str | None]) -> dict:
    """Euro gain of each position over the euros spent buying: the contributions add up to the total.

    gain = value today + what sales raised + net dividends − what purchases cost, all in euros;
    contribution = gain / total bought. ``rates`` holds each movement's rate by its index in ``lots``."""
    bought_total = 0.0
    gains: dict[str, float] = {}
    for index, lot in enumerate(lots):
        euros = movement_eur(lot, rates[index])
        if kind(lot) == "buy":
            bought_total += euros
        gains[lot["symbol"]] = gains.get(lot["symbol"], 0.0) - euros
    for symbol, value in final_values.items():
        gains[symbol] = gains.get(symbol, 0.0) + value
    if bought_total <= 0:
        return {"status": "no_purchases"}
    positions = [{"symbol": symbol, "sector": sectors.get(symbol), "gain_eur": gain,
                  "contribution_pp": gain / bought_total * 100, "open": symbol in final_values}
                 for symbol, gain in gains.items()]
    by_sector: dict[str, float] = {}
    for symbol, gain in gains.items():
        sector = sectors.get(symbol) or "Sin sector"
        by_sector[sector] = by_sector.get(sector, 0.0) + gain
    total = sum(gains.values())
    return {"status": "ok", "bought_eur": bought_total, "gain_eur": total, "return_on_bought": total / bought_total,
            "positions": sorted(positions, key=lambda row: (-row["gain_eur"], row["symbol"])),
            "sectors": sorted(({"sector": sector, "gain_eur": gain, "contribution_pp": gain / bought_total * 100}
                               for sector, gain in by_sector.items()), key=lambda row: -row["gain_eur"])}


def evaluate(lots: list[dict], closes: dict[str, pd.Series], euros_per_unit: dict[str, pd.Series],
             spy_adjusted: pd.Series, sectors: dict[str, str | None], as_of: date) -> dict:
    """Everything the «Evolución» section shows; a blocked or empty series says why."""
    sessions = spy_adjusted.dropna().index
    sessions = sessions[sessions <= pd.Timestamp(as_of)]
    result = history(lots, closes, euros_per_unit, sessions)
    base = {"version": VERSION, "as_of": as_of.isoformat(), "status": result["status"]}
    if result["status"] != "ok":
        return base | {"blocked": result.get("blocked", []), "gaps": result.get("gaps", [])}
    daily = result["daily"]
    last = daily.index[-1]
    final_values = {column[2:]: float(daily.loc[last, column]) for column in daily.columns
                    if column.startswith("v:") and pd.notna(daily.loc[last, column])}
    ordered = sorted(lots, key=lambda row: (row["purchase_date"], row.get("id") or 0))
    rates = {index: _rate(lot, euros_per_unit, pd.Timestamp(lot["purchase_date"])) or 0.0
             for index, lot in enumerate(ordered)}
    usd = euros_per_unit.get("USD", pd.Series(dtype=float))
    return base | {
        "portfolio": risk(daily),
        "benchmark": benchmark(daily, spy_adjusted, usd),
        "attribution": attribution(ordered, final_values, rates, sectors),
        "gaps": result["gaps"], "gap_sessions": len(result["gaps"]),
        "pending_eur": result["pending_eur"],
    }
