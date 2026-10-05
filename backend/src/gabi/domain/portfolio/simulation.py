"""Carteras simuladas locales (nunca conectadas a un bróker): ejecución en la primera sesión con
cierre en caché, contabilidad con costes y divisa, curva diaria y resumen frente al SPY."""

from datetime import date

import exchange_calendars as xcals
import pandas as pd

MARKETS = {"XNYS": "NYSE / Nasdaq (EE. UU.)", "XETR": "Xetra (Alemania)",
           "XLON": "Londres", "XMAD": "Madrid", "XPAR": "París"}


def execution_quote(history: pd.DataFrame, requested_date: str, market: str, today: date) -> dict:
    target = pd.Timestamp(requested_date)
    if target.date() > today:
        raise ValueError("No se puede simular una operación futura.")
    if market not in MARKETS:
        raise ValueError("Mercado no admitido.")
    session = xcals.get_calendar(market).date_to_session(target, direction="next")
    if session.date() > today:
        raise ValueError("Todavía no hay una sesión bursátil cerrada para esta fecha.")
    if history.empty or "adj_close" not in history:
        raise ValueError("No hay precios descargados para este símbolo.")
    if session not in history.index:
        raise ValueError(f"Falta el precio de la primera sesión bursátil ({session.date()}).")
    row = history.loc[session]
    if pd.isna(row["close"]) or pd.isna(row["adj_close"]) or row["close"] <= 0 or row["adj_close"] <= 0:
        raise ValueError("El precio de ejecución no es válido.")
    return {"date": session.date().isoformat(), "close": float(row["close"]),
            "adj_close": float(row["adj_close"])}


def _price_at(histories: dict, symbol: str, day: str) -> float:
    history = histories.get(symbol)
    if history is None or history.empty or pd.Timestamp(day) not in history.index:
        raise ValueError(f"Falta el precio ajustado de {symbol} el {day}.")
    value = history.loc[pd.Timestamp(day), "adj_close"]
    if pd.isna(value) or value <= 0:
        raise ValueError(f"Precio ajustado inválido de {symbol} el {day}.")
    return float(value)


def fx_symbol(quote_currency: str, base_currency: str) -> str | None:
    if quote_currency not in ("USD", "EUR", "GBP") or base_currency not in ("USD", "EUR"):
        raise ValueError("Divisa no admitida.")
    if quote_currency == base_currency:
        return None
    if (quote_currency, base_currency) not in {("EUR", "USD"), ("USD", "EUR"),
                                               ("GBP", "USD"), ("GBP", "EUR")}:
        raise ValueError("Par de divisas no admitido.")
    return f"{quote_currency}{base_currency}=X"


def fx_at(histories: dict, quote_currency: str, base_currency: str, day) -> float:
    pair = fx_symbol(quote_currency, base_currency)
    if pair is None:
        return 1.0
    history = histories.get(pair)
    if history is None or history.empty:
        raise ValueError(f"Falta el histórico de divisa {pair}.")
    recent = history.loc[(history.index <= pd.Timestamp(day))
                         & (history.index >= pd.Timestamp(day) - pd.Timedelta(days=7)), "close"].dropna()
    if recent.empty or recent.iloc[-1] <= 0:
        raise ValueError(f"Falta el cambio {pair} para {day}.")
    return float(recent.iloc[-1])


def _cash_delta(trade, base_currency: str) -> float:
    rate = float(trade.get("fx_rate", 1))
    fee = float(trade.get("fx_fee_bps", 0)) / 10000
    amount = float(trade["notional"])
    commission = float(trade["commission"])
    half = float(trade["spread_bps"]) / 20000
    if trade["side"] == "BUY":
        return -(amount + commission) * rate * (1 + fee)
    return (amount * (1 - half) - commission) * rate * (1 - fee)


def replay(portfolio: dict, trades: pd.DataFrame, histories: dict) -> tuple[float, dict]:
    """Contabilidad en unidades de rentabilidad total; rechaza tanto quedarse a deber como vender en corto."""
    cash = float(portfolio["initial_cash"])
    base = portfolio.get("base_currency", "USD")
    units: dict[str, float] = {}
    if trades.empty:
        return cash, units
    for _, trade in trades.sort_values(["execution_date", "id"]).iterrows():
        symbol = trade["symbol"]
        adj = _price_at(histories, symbol, trade["execution_date"])
        half = float(trade["spread_bps"]) / 20000
        notional = float(trade["notional"])
        if trade["side"] == "BUY":
            cost = -_cash_delta(trade, base)
            if cash + 1e-8 < cost:
                raise ValueError(f"Efectivo insuficiente para comprar {symbol} el {trade['execution_date']}.")
            cash -= cost
            units[symbol] = units.get(symbol, 0.0) + notional / (adj * (1 + half))
        elif trade["side"] == "SELL":
            quantity = notional / adj
            if units.get(symbol, 0.0) + 1e-8 < quantity:
                raise ValueError(f"Posición insuficiente para vender {symbol} el {trade['execution_date']}.")
            units[symbol] = max(0.0, units[symbol] - quantity)
            cash += _cash_delta(trade, base)
        else:
            raise ValueError("Tipo de operación desconocido.")
    return cash, units


def history(portfolio: dict, trades: pd.DataFrame, histories: dict, today: date) -> dict:
    """Valor diario de la cartera en su divisa base hasta ``today``, con los precios ya cargados."""
    if trades.empty:
        return {"curve": pd.DataFrame(), "cash": portfolio["initial_cash"], "positions": {},
                "trades": trades, "portfolio": portfolio}
    symbols = trades["symbol"].unique().tolist()
    base = portfolio["base_currency"]
    currencies = {s: trades.loc[trades["symbol"] == s, "quote_currency"].iloc[0] for s in symbols}
    if any(trades.loc[trades["symbol"] == s, "quote_currency"].nunique() > 1 for s in symbols):
        raise ValueError("Un mismo ticker no puede cambiar de divisa dentro de una cartera.")
    start = pd.Timestamp(trades["execution_date"].min())
    end = min(pd.Timestamp(today), max((h.index.max() for h in histories.values() if not h.empty), default=start))
    calendar = pd.DatetimeIndex([])
    for market in trades["market"].unique():
        calendar = calendar.union(xcals.get_calendar(market).sessions_in_range(start, end))
    calendar = calendar.union(pd.to_datetime(trades["execution_date"])).sort_values()
    cash = float(portfolio["initial_cash"])
    units: dict[str, float] = {}
    rows = []
    sorted_trades = trades.sort_values(["execution_date", "id"])
    next_trade = 0
    for day in calendar:
        while next_trade < len(sorted_trades) and pd.Timestamp(sorted_trades.iloc[next_trade]["execution_date"]) <= day:
            t = sorted_trades.iloc[next_trade]
            adj = _price_at(histories, t["symbol"], t["execution_date"])
            half = float(t["spread_bps"]) / 20000
            if t["side"] == "BUY":
                cash += _cash_delta(t, base)
                units[t["symbol"]] = units.get(t["symbol"], 0) + t["notional"] / (adj * (1 + half))
            else:
                units[t["symbol"]] -= t["notional"] / adj
                cash += _cash_delta(t, base)
            next_trade += 1
        value = cash
        complete = True
        for symbol, quantity in units.items():
            if quantity <= 1e-9:
                continue
            h = histories[symbol]
            recent = h.loc[(h.index <= day) & (h.index >= day - pd.Timedelta(days=7)), "adj_close"].dropna()
            if recent.empty:
                complete = False
                break
            try:
                rate = fx_at(histories, currencies[symbol], base, day)
            except ValueError:
                complete = False
                break
            value += quantity * float(recent.iloc[-1]) * rate
        rows.append((day, value if complete else float("nan"), cash))
    curve = pd.DataFrame(rows, columns=["date", "value", "cash"]).set_index("date")
    replay(portfolio, trades, histories)
    return {"curve": curve, "cash": cash, "positions": {s: q for s, q in units.items() if q > 1e-9},
            "trades": trades, "portfolio": portfolio, "histories": histories}


def summarize(result: dict) -> dict:
    curve = result["curve"]
    if curve.empty:
        return {}
    initial = float(result["portfolio"]["initial_cash"])
    values = curve["value"].dropna()
    if values.empty:
        return {"status": "missing_prices"}
    latest_day = curve.index.max()
    if pd.isna(curve.loc[latest_day, "value"]):
        return {"status": "missing_prices"}
    benchmark = result["histories"].get("SPY", pd.DataFrame())
    benchmark_return = None
    if not benchmark.empty:
        b = benchmark.loc[(benchmark.index >= curve.index.min()) & (benchmark.index <= latest_day), "adj_close"].dropna()
        if (len(b) >= 2 and b.iloc[0] > 0
                and (b.index[0] - curve.index.min()).days <= 7
                and (latest_day - b.index[-1]).days <= 7):
            half_spread = result["portfolio"]["spread_bps"] / 20000
            fee_factor = max(0, initial - result["portfolio"]["etf_commission"]) / initial
            try:
                fx0 = fx_at(result["histories"], "USD", result["portfolio"]["base_currency"], b.index[0])
                fx1 = fx_at(result["histories"], "USD", result["portfolio"]["base_currency"], b.index[-1])
                benchmark_return = float(fee_factor * b.iloc[-1] * fx1 / (b.iloc[0] * fx0) / (1 + half_spread) - 1)
            except ValueError:
                pass
    # Una valoración ausente es un hueco de datos, no una sesión con retorno cero.
    daily = curve["value"].pct_change(fill_method=None).dropna()
    sharpe = max_drawdown = None
    if len(daily) >= 30 and curve["value"].notna().all():
        import quantstats as qs
        if result["trades"]["market"].nunique() == 1:
            sharpe = float(qs.stats.sharpe(daily))
        max_drawdown = float(qs.stats.max_drawdown(daily))
    return {"status": "complete", "as_of": latest_day.date().isoformat(),
            "value": float(values.iloc[-1]), "return": float(values.iloc[-1] / initial - 1),
            "benchmark_return": benchmark_return, "sharpe": sharpe,
            "max_drawdown": max_drawdown}
