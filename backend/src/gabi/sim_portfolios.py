"""Carteras locales (nunca conectadas a un bróker) de operaciones simuladas
y fechadas de acciones/ETF."""
from datetime import UTC, date, datetime
from math import isfinite

import exchange_calendars as xcals
import pandas as pd

from . import storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS sim_portfolios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    initial_cash REAL NOT NULL,
    stock_commission REAL NOT NULL,
    etf_commission REAL NOT NULL,
    spread_bps REAL NOT NULL,
    created_at TEXT NOT NULL,
    base_currency TEXT NOT NULL DEFAULT 'USD'
);
CREATE TABLE IF NOT EXISTS sim_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    side TEXT NOT NULL,
    requested_date TEXT NOT NULL,
    execution_date TEXT NOT NULL,
    reference_close REAL NOT NULL,
    notional REAL NOT NULL,
    commission REAL NOT NULL,
    spread_bps REAL NOT NULL,
    created_at TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'XNYS',
    quote_currency TEXT NOT NULL DEFAULT 'USD',
    fx_rate REAL NOT NULL DEFAULT 1,
    fx_fee_bps REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (portfolio_id) REFERENCES sim_portfolios(id)
);
CREATE INDEX IF NOT EXISTS idx_sim_trades_portfolio_date
ON sim_trades(portfolio_id, execution_date, id);
"""

MARKETS = {"XNYS": "NYSE / Nasdaq (EE. UU.)", "XETR": "Xetra (Alemania)",
           "XLON": "Londres", "XMAD": "Madrid", "XPAR": "París"}


def _init(conn):
    conn.executescript(SCHEMA)
    for table, columns in {
        "sim_portfolios": {"base_currency": "TEXT NOT NULL DEFAULT 'USD'"},
        "sim_trades": {"market": "TEXT NOT NULL DEFAULT 'XNYS'",
                       "quote_currency": "TEXT NOT NULL DEFAULT 'USD'",
                       "fx_rate": "REAL NOT NULL DEFAULT 1", "fx_fee_bps": "REAL NOT NULL DEFAULT 0"},
    }.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_portfolio(name: str, initial_cash: float, stock_commission: float = 1.0,
                     etf_commission: float = 0.0, spread_bps: float = 10.0,
                     base_currency: str = "USD") -> int:
    name = name.strip()
    if (not name or any(not isfinite(x) or x < 0 for x in
                        (initial_cash, stock_commission, etf_commission, spread_bps))
            or initial_cash == 0
            or base_currency not in ("USD", "EUR")):
        raise ValueError("Indica nombre, capital positivo y costes no negativos.")
    with storage.get_connection() as conn:
        _init(conn)
        try:
            cur = conn.execute(
                "INSERT INTO sim_portfolios (name, initial_cash, stock_commission, etf_commission, spread_bps, created_at, base_currency) "
                "VALUES (?,?,?,?,?,?,?)",
                (name, initial_cash, stock_commission, etf_commission, spread_bps,
                 datetime.now(UTC).isoformat(), base_currency),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ValueError("Ya existe una cartera con ese nombre.") from exc
            raise
        conn.commit()
        return cur.lastrowid


def list_portfolios() -> pd.DataFrame:
    with storage.get_connection() as conn:
        _init(conn)
        return pd.read_sql_query("SELECT * FROM sim_portfolios ORDER BY id DESC", conn)


def get_portfolio(portfolio_id: int) -> dict:
    portfolios = list_portfolios()
    matched = portfolios[portfolios["id"] == portfolio_id]
    if matched.empty:
        raise ValueError("La cartera no existe.")
    return matched.iloc[0].to_dict()


def list_trades(portfolio_id: int) -> pd.DataFrame:
    with storage.get_connection() as conn:
        _init(conn)
        return pd.read_sql_query(
            "SELECT * FROM sim_trades WHERE portfolio_id=? ORDER BY execution_date, id",
            conn, params=(portfolio_id,),
        )


def execution_quote(symbol: str, requested_date: str, market: str = "XNYS") -> dict:
    """Usa la primera sesión del mercado elegido; nunca se salta una cotización que falte en caché (falla en vez de aproximar)."""
    target = pd.Timestamp(requested_date)
    if target.date() > date.today():
        raise ValueError("No se puede simular una operación futura.")
    if market not in MARKETS:
        raise ValueError("Mercado no admitido.")
    session = xcals.get_calendar(market).date_to_session(target, direction="next")
    if session.date() > date.today():
        raise ValueError("Todavía no hay una sesión bursátil cerrada para esta fecha.")
    history = storage.get_prices(symbol)
    if history.empty or "adj_close" not in history:
        raise ValueError("No hay precios descargados para este símbolo.")
    if session not in history.index:
        raise ValueError(f"Falta el precio de {symbol} en la primera sesión bursátil ({session.date()}).")
    day, row = session, history.loc[session]
    if (pd.isna(row["close"]) or pd.isna(row["adj_close"])
            or row["close"] <= 0 or row["adj_close"] <= 0):
        raise ValueError("El precio de ejecución no es válido.")
    return {"date": day.date().isoformat(), "close": float(row["close"]),
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


def _fx_at(histories: dict, quote_currency: str, base_currency: str, day) -> float:
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
    units = {}
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


def add_trade(portfolio_id: int, symbol: str, asset_type: str, side: str,
              requested_date: str, notional: float, market: str = "XNYS",
              quote_currency: str = "USD", commission: float | None = None,
              spread_bps: float | None = None, fx_rate: float | None = None,
              fx_fee_bps: float = 0) -> dict:
    portfolio = get_portfolio(portfolio_id)
    symbol = symbol.upper().strip()
    if (not symbol or asset_type not in ("STOCK", "ETF") or side not in ("BUY", "SELL")
            or not isfinite(notional) or notional <= 0):
        raise ValueError("Símbolo, instrumento, operación o importe inválidos.")
    pair = fx_symbol(quote_currency, portfolio["base_currency"])
    quote = execution_quote(symbol, requested_date, market)
    commission = (portfolio["etf_commission"] if asset_type == "ETF" else portfolio["stock_commission"]) if commission is None else commission
    spread_bps = portfolio["spread_bps"] if spread_bps is None else spread_bps
    if any(not isfinite(x) or x < 0 for x in (commission, spread_bps, fx_fee_bps)):
        raise ValueError("Los costes no pueden ser negativos.")
    if pair:
        if fx_rate is None:
            fx_rate = _fx_at(storage.get_prices_multi([pair]), quote_currency,
                             portfolio["base_currency"], quote["date"])
        if not isfinite(fx_rate) or fx_rate <= 0:
            raise ValueError("El tipo de cambio debe ser positivo.")
    else:
        fx_rate = 1.0
        fx_fee_bps = 0.0
    existing = list_trades(portfolio_id)
    new_id = int(existing["id"].max()) + 1 if not existing.empty else 1
    new_trade = {
        "id": new_id, "portfolio_id": portfolio_id, "symbol": symbol,
        "asset_type": asset_type, "side": side, "requested_date": requested_date,
        "execution_date": quote["date"], "reference_close": quote["close"],
        "notional": float(notional), "commission": float(commission),
        "spread_bps": float(spread_bps), "market": market,
        "quote_currency": quote_currency, "fx_rate": float(fx_rate), "fx_fee_bps": float(fx_fee_bps),
        "created_at": datetime.now(UTC).isoformat(),
    }
    combined = pd.concat([existing, pd.DataFrame([new_trade])], ignore_index=True)
    symbols = combined["symbol"].unique().tolist()
    histories = storage.get_prices_multi(symbols)
    replay(portfolio, combined, histories)  # valida todo el histórico antes de escribir nada
    with storage.get_connection() as conn:
        conn.execute(
            "INSERT INTO sim_trades (portfolio_id, symbol, asset_type, side, requested_date, execution_date, "
            "reference_close, notional, commission, spread_bps, created_at, market, quote_currency, fx_rate, fx_fee_bps) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(new_trade[k] for k in ("portfolio_id", "symbol", "asset_type", "side", "requested_date",
                                         "execution_date", "reference_close", "notional", "commission",
                                         "spread_bps", "created_at", "market", "quote_currency", "fx_rate", "fx_fee_bps")),
        )
        conn.commit()
    return new_trade


def undo_last_trade(portfolio_id: int) -> bool:
    """Elimina solo la última operación simulada introducida; conserva un libro de operaciones restante válido."""
    trades = list_trades(portfolio_id)
    if trades.empty:
        return False
    last_id = int(trades["id"].max())
    remaining = trades[trades["id"] != last_id]
    replay(get_portfolio(portfolio_id), remaining,
           storage.get_prices_multi(remaining["symbol"].unique().tolist()) if not remaining.empty else {})
    with storage.get_connection() as conn:
        conn.execute("DELETE FROM sim_trades WHERE id=? AND portfolio_id=?", (last_id, portfolio_id))
        conn.commit()
    return True


def portfolio_history(portfolio_id: int) -> dict:
    portfolio = get_portfolio(portfolio_id)
    trades = list_trades(portfolio_id)
    if trades.empty:
        return {"curve": pd.DataFrame(), "cash": portfolio["initial_cash"], "positions": {},
                "trades": trades, "portfolio": portfolio}
    symbols = trades["symbol"].unique().tolist()
    base = portfolio["base_currency"]
    currencies = {s: trades.loc[trades["symbol"] == s, "quote_currency"].iloc[0] for s in symbols}
    if any(trades.loc[trades["symbol"] == s, "quote_currency"].nunique() > 1 for s in symbols):
        raise ValueError("Un mismo ticker no puede cambiar de divisa dentro de una cartera.")
    pairs = {fx_symbol(currency, base) for currency in currencies.values()}
    pairs.add(fx_symbol("USD", base))
    histories = storage.get_prices_multi(symbols + ["SPY"] + [p for p in pairs if p])
    start = pd.Timestamp(trades["execution_date"].min())
    end = min(pd.Timestamp(date.today()), max((h.index.max() for h in histories.values() if not h.empty), default=start))
    calendar = pd.DatetimeIndex([])
    for market in trades["market"].unique():
        calendar = calendar.union(xcals.get_calendar(market).sessions_in_range(start, end))
    calendar = calendar.union(pd.to_datetime(trades["execution_date"])).sort_values()
    cash = float(portfolio["initial_cash"])
    units = {}
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
                rate = _fx_at(histories, currencies[symbol], base, day)
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
                fx0 = _fx_at(result["histories"], "USD", result["portfolio"]["base_currency"], b.index[0])
                fx1 = _fx_at(result["histories"], "USD", result["portfolio"]["base_currency"], b.index[-1])
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


def sma_backtest(symbol: str, start: str, end: str, fast: int, slow: int,
                 cash: float, commission: float, spread_bps: float) -> dict:
    """Cruce de medias móviles con Backtesting.py: la señal se calcula al cierre y se ejecuta en la siguiente sesión."""
    if not (2 <= fast < slow) or cash <= 0 or commission < 0 or spread_bps < 0:
        raise ValueError("Parámetros de backtesting inválidos.")
    from backtesting import Backtest, Strategy

    history = storage.get_prices(symbol).loc[start:end]
    if len(history) < slow + 30:
        raise ValueError("No hay sesiones suficientes para este periodo y estas medias.")
    data = history.rename(columns={"open": "Open", "high": "High", "low": "Low",
                                   "close": "Close", "volume": "Volume"})
    data = data[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if len(data) < slow + 30:
        raise ValueError("Faltan precios completos para el backtest.")

    def ma(values, window):
        return pd.Series(values).rolling(window).mean().to_numpy()

    class SmaCross(Strategy):
        def init(self):
            self.fast_ma = self.I(ma, self.data.Close, fast)
            self.slow_ma = self.I(ma, self.data.Close, slow)

        def next(self):
            if (self.fast_ma[-2] <= self.slow_ma[-2]
                    and self.fast_ma[-1] > self.slow_ma[-1] and not self.position):
                self.buy(size=.95)
            elif (self.fast_ma[-2] >= self.slow_ma[-2]
                  and self.fast_ma[-1] < self.slow_ma[-1] and self.position):
                self.position.close()

    bt = Backtest(data, SmaCross, cash=cash, commission=(commission, 0),
                  spread=spread_bps / 10000, exclusive_orders=True, finalize_trades=True)
    stats = bt.run()
    return {"strategy_return": float(stats["Return [%]"]) / 100,
            "buy_hold_return": float(stats["Buy & Hold Return [%]"]) / 100,
            "max_drawdown": float(stats["Max. Drawdown [%]"]) / 100,
            "trades": int(stats["# Trades"]), "equity_curve": stats["_equity_curve"]["Equity"]}
