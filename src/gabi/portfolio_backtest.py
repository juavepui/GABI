"""Motor de backtest V2: contabilidad real de cartera (acciones + caja),
turnover y coste real por operación, y curva NAV diaria genuina -- no una
reconstrucción de porcentajes escalada a posteriori como hace
`multifactor_backtest.daily_capital_curve` (V1).

`multifactor_backtest.py` (V1) NO se toca: sigue siendo el motor que
reprodujo `HIPOTESIS_CONGELADA.md` y todo el histórico de `README.md`, y
debe seguir dando exactamente los mismos números. Este módulo reutiliza por
import lo que ya es correcto allí (`_sample_symbols`, el guard de reciclaje
de ticker point-in-time, `sharpe_standard_error`) en vez de duplicarlo.

Convención de coste: la MISMA que `sim_portfolios.py` (Carteras Simuladas) —
comisión fija en dólares por operación + spread proporcional que encarece la
compra / reduce lo cobrado en la venta (`_apply_trade`, ver
`sim_portfolios._cash_delta`/`replay`). No se inventa un modelo nuevo."""
from datetime import date

import exchange_calendars as xcals
import pandas as pd

from . import broker_costs, data_quality, identity, screener_asof, universe
from . import multifactor_backtest as v1

_CALENDAR = "XNYS"


def _apply_trade(cash: float, shares: dict, symbol: str, side: str, notional: float,
                 price: float, commission_usd: float, spread_bps: float) -> float:
    """Compra/vende `notional` (en dólares, al precio `price`) de `symbol`,
    mutando `shares` in-place y devolviendo la caja resultante. `notional`
    <= 0 no hace nada (evita comisión por una operación de importe nulo)."""
    if notional <= 1e-9:
        return cash
    half = spread_bps / 20000
    if side == "BUY":
        cash -= notional + commission_usd
        shares[symbol] = shares.get(symbol, 0.0) + notional / (price * (1 + half))
    elif side == "SELL":
        quantity = notional / price
        cash += notional * (1 - half) - commission_usd
        remaining = shares.get(symbol, 0.0) - quantity
        if remaining <= 1e-9:
            shares.pop(symbol, None)
        else:
            shares[symbol] = remaining
    else:
        raise ValueError(f"side desconocido: {side}")
    return cash


def _rebalance_to_weights(cash: float, shares: dict, target_weights: dict, entry_price: dict,
                          commission_usd: float, spread_bps: float) -> dict:
    """Rebalanceo real a CUALQUIER conjunto de pesos objetivo (que sumen
    ~1, no necesariamente equiponderado -- ver `portfolio_lab.py`, que
    reutiliza esto con Inverse Volatility/Minimum Variance/Score-weighted/
    Risk Parity/etc.): vende lo que sale de la selección, compra lo nuevo,
    y ajusta (compra/vende solo el delta) lo que se mantiene para volver a
    SU peso objetivo -- la "variación de peso" que no modelaba V1 (que no
    cobraba nada a lo mantenido, pero tampoco lo reequilibraba). Solo paga
    comisión/spread sobre lo realmente negociado, nunca sobre el 100% de
    una posición que sigue en cartera."""
    current_symbols = set(shares.keys())
    picks_set = set(target_weights)
    held = current_symbols & picks_set
    sold = current_symbols - picks_set
    bought = picks_set - current_symbols

    portfolio_value = cash + sum(shares[s] * entry_price[s] for s in shares)

    traded_notional = 0.0
    trades_executed = 0

    for s in sorted(sold):
        notional = shares[s] * entry_price[s]
        before = cash
        cash = _apply_trade(cash, shares, s, "SELL", notional, entry_price[s], commission_usd, spread_bps)
        if cash != before:
            traded_notional += notional
            trades_executed += 1

    for s in sorted(held):
        target_value = target_weights[s] * portfolio_value
        current_value = shares[s] * entry_price[s]
        delta = target_value - current_value
        side = "BUY" if delta > 0 else "SELL"
        before = cash
        cash = _apply_trade(cash, shares, s, side, abs(delta), entry_price[s], commission_usd, spread_bps)
        if cash != before:
            traded_notional += abs(delta)
            trades_executed += 1

    for s in sorted(bought):
        target_value = target_weights[s] * portfolio_value
        before = cash
        cash = _apply_trade(cash, shares, s, "BUY", target_value, entry_price[s], commission_usd, spread_bps)
        if cash != before:
            traded_notional += target_value
            trades_executed += 1

    turnover_pct = (traded_notional / portfolio_value * 100) if portfolio_value > 0 else 0.0
    return {"cash": cash, "turnover_pct": turnover_pct,
            "comision_pagada": trades_executed * commission_usd,
            "held": held, "sold": sold, "bought": bought}


def _rebalance(cash: float, shares: dict, picks: list, entry_price: dict, top_n: int,
              commission_usd: float, spread_bps: float) -> dict:
    """Rebalanceo equiponderado -- caso particular de `_rebalance_to_weights`
    con `{s: 1/top_n for s in picks}`. Ver esa función para el detalle."""
    target_weights = {s: 1.0 / top_n for s in picks} if top_n else {}
    return _rebalance_to_weights(cash, shares, target_weights, entry_price, commission_usd, spread_bps)


def _daily_segment(cash: float, shares: dict, entry_session: pd.Timestamp,
                   exit_session: pd.Timestamp, sessions: pd.DatetimeIndex, *, owners: dict | None = None) -> pd.Series:
    """Valora caja + Σ(acciones × adj_close del día) sesión a sesión --
    mismo patrón que `sim_portfolios.portfolio_history()`. Se calcula
    SIEMPRE, incluso si el rebalanceo de ese periodo se saltó por falta de
    cobertura: la cartera sigue flotando con lo que ya tenía (a diferencia
    de V1, donde un periodo saltado deja un hueco en la curva)."""
    segment = pd.Series(cash, index=sessions, dtype=float)
    if not shares:
        return segment
    histories = identity.backtest_prices(list(shares.keys()), entry_session.date().isoformat(), owners)
    for symbol, qty in shares.items():
        h = histories.get(symbol, pd.DataFrame())
        if owners and owners.get(symbol):
            if h.empty or h["adj_close"].reindex(sessions).isna().any():
                raise ValueError(f"Missing attributed prices for held entity {owners[symbol]}")
        if h.empty or "adj_close" not in h:
            continue
        price_series = h["adj_close"].reindex(sessions).ffill().bfill()
        segment = segment.add(qty * price_series.fillna(0.0), fill_value=0.0)
    return segment


VALID_MODES = ("validation", "fast_dev")


def run(start: str, end: str, months: int = 3, top_n: int = 20, max_symbols: int | None = None,
        mode: str = "validation", initial_capital: float = 100_000.0,
        commission_usd: float = broker_costs.STOCK_FEE_USD,
        spread_bps: float = 10.0, min_coverage: float = .7, min_universe_coverage: float = .5) -> dict:
    """Backtest V2 con contabilidad real de cartera. Mismo bucle de
    reconstrucción point-in-time que `multifactor_backtest.run()`
    (universo histórico + ranking SEC EDGAR a fecha), pero el resultado de
    cada rebalanceo es una operación real sobre acciones/caja (`_rebalance`)
    en vez de un retorno porcentual agregado, y la curva de capital es un
    walk-forward diario real (`_daily_segment`), no una reconstrucción
    escalada.

    `mode` (pedido explícitamente por el usuario, paso 2 de la hoja de ruta
    V2): seleccionar las mejores N de una muestra aleatoria de 200 empresas
    no es la misma estrategia que seleccionar las mejores N del S&P 500
    completo -- útil para iterar rápido, pero no es evidencia de la
    estrategia real. Dos modos, mutuamente excluyentes con `max_symbols`:
    - `"validation"` (por defecto): universo histórico COMPLETO, sin
      muestreo -- exige `max_symbols=None`. Es el único modo cuyo resultado
      debería citarse como evidencia de la estrategia.
    - `"fast_dev"`: exige `max_symbols` (ej. 50/100/200) -- para iterar
      rápido en desarrollo. El resultado incluye `mode` explícitamente para
      que no se pueda confundir sin querer con una validación real.

    `commission_usd`/`spread_bps`: mismo modelo de coste que
    `sim_portfolios.py`, calibrado en `broker_costs.py` (por defecto 1 USD
    fijo por operación + 10pb de spread). `commission_usd=0` recupera un
    modelo puramente proporcional si se quiere barrer solo `spread_bps`
    (25/50pb) para sensibilidad a costes, comparable con las tablas de V1."""
    if mode not in VALID_MODES:
        raise ValueError(f"mode debe ser uno de {VALID_MODES}.")
    if mode == "validation" and max_symbols is not None:
        raise ValueError("mode='validation' no permite muestreo (max_symbols debe ser None) -- "
                         "usa mode='fast_dev' para pruebas rápidas con un subconjunto.")
    if mode == "fast_dev" and max_symbols is None:
        raise ValueError("mode='fast_dev' necesita max_symbols (ej. 50/100/200) -- "
                         "usa mode='validation' para el universo histórico completo.")
    if not 1 <= months <= 12 or not 1 <= top_n <= 50:
        raise ValueError("Parámetros del backtest inválidos.")
    if not 0 < min_coverage <= 1 or not 0 < min_universe_coverage <= 1:
        raise ValueError("La cobertura debe estar entre 0 y 1.")
    if initial_capital <= commission_usd:
        raise ValueError("initial_capital debe ser mayor que commission_usd.")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if start_ts >= end_ts or end_ts > pd.Timestamp(date.today()):
        raise ValueError("El intervalo debe terminar después del inicio y no superar hoy.")

    calendar = xcals.get_calendar(_CALENDAR)
    boundaries = []
    current = start_ts
    while current + pd.DateOffset(months=months) <= end_ts:
        boundaries.append(current)
        current += pd.DateOffset(months=months)
    boundaries.append(current)
    if len(boundaries) < 2:
        raise ValueError("El intervalo no contiene ningún rebalanceo completo.")

    cash = float(initial_capital)
    shares: dict[str, float] = {}
    owners: dict[str, str] = {}
    rows = []
    skipped = []
    quality_by_date = {}
    nav_pieces = []

    for i in range(len(boundaries) - 1):
        as_of = boundaries[i]
        as_of_str = as_of.date().isoformat()
        signal_session = calendar.date_to_session(as_of, direction="previous")
        entry_session = calendar.next_session(signal_session)
        exit_session = calendar.date_to_session(boundaries[i + 1], direction="next")

        try:
            if exit_session > pd.Timestamp(date.today()):
                raise ValueError(f"El periodo iniciado en {as_of.date()} aún no tiene salida.")
            membership = universe.get_sp500_constituents_asof(as_of_str)
            if not membership["is_exact"]:
                raise ValueError(membership["note"])
            symbols = v1._sample_symbols(membership["symbols"], max_symbols)
            ranked = screener_asof.build_ranking_as_of(as_of_str, symbols=symbols)["table"]
            quality_by_date[as_of_str] = data_quality.ranking_quality(ranked)
            eligible = ranked[(ranked["composite_score"].notna())
                              & (ranked["score_coverage"] >= min_coverage)]
            if len(eligible) / len(symbols) < min_universe_coverage:
                raise ValueError(f"cobertura insuficiente del universo ({len(eligible)}/{len(symbols)})")
            picks = eligible.index.tolist()[:top_n]
            if len(picks) < top_n:
                raise ValueError(f"solo {len(picks)}/{top_n} candidatas con cobertura suficiente")

            needed = sorted(set(shares.keys()) | set(picks))
            for symbol in needed:
                owner = identity.resolve(symbol, as_of_str)["entity_id"]
                if symbol in shares and owners.get(symbol) and owner and owners[symbol] != owner:
                    raise ValueError(f"Ticker reassigned while holding {symbol}")
                if owner and (symbol not in owners or symbol not in shares):
                    owners[symbol] = owner
            histories = identity.backtest_prices(needed, as_of_str, owners)
            last_filed = identity.last_filings(needed, as_of=exit_session.date().isoformat())
            missing, recycled, entry_price = [], [], {}
            for s in needed:
                h = histories.get(s, pd.DataFrame())
                if (h.empty or entry_session not in h.index or pd.isna(h.loc[entry_session, "adj_close"])
                        or h.loc[entry_session, "adj_close"] <= 0):
                    missing.append(s)
                    continue
                if s in last_filed:
                    gap_days = (exit_session - pd.Timestamp(last_filed[s])).days
                    if gap_days > v1._MAX_DAYS_WITHOUT_FILING:
                        recycled.append(s)
                        continue
                entry_price[s] = float(h.loc[entry_session, "adj_close"])
            if missing:
                raise ValueError(f"Faltan precios ajustados en entrada ({entry_session.date()}): "
                                 f"{', '.join(missing)}")
            if recycled:
                raise ValueError(f"Ticker probablemente reciclado en {exit_session.date()}: "
                                 f"{', '.join(recycled)}")

            result = _rebalance(cash, shares, picks, entry_price, top_n, commission_usd, spread_bps)
            cash = result["cash"]
            rows.append({
                "fecha": as_of_str, "hasta": exit_session.date().isoformat(),
                "held": ", ".join(sorted(result["held"])), "sold": ", ".join(sorted(result["sold"])),
                "bought": ", ".join(sorted(result["bought"])), "turnover_pct": result["turnover_pct"],
                "comision_pagada": result["comision_pagada"],
            })
        except (ValueError, RuntimeError) as exc:
            skipped.append({"fecha": as_of_str, "motivo": str(exc)})

        sessions = calendar.sessions_in_range(entry_session, exit_session)
        nav_pieces.append(_daily_segment(cash, shares, entry_session, exit_session, sessions, owners=owners))

    if not rows:
        raise ValueError("Ningún periodo del rango tiene datos suficientes — "
                         f"se saltaron los {len(skipped)} periodos por falta de cobertura.")

    nav_curve = pd.concat(nav_pieces).sort_index()
    nav_curve = nav_curve[~nav_curve.index.duplicated(keep="last")]
    periods = pd.DataFrame(rows)
    nav_curve_spy = buy_and_hold_curve("SPY", nav_curve.index[0].date().isoformat(),
                                       nav_curve.index[-1].date().isoformat(),
                                       initial_capital=initial_capital,
                                       commission_usd=commission_usd, spread_bps=spread_bps)

    return {
        "data_quality": quality_by_date,
        "mode": mode, "periods": periods, "skipped": skipped,
        "nav_curve": nav_curve, "nav_curve_spy": nav_curve_spy,
        "turnover_medio": float(periods["turnover_pct"].mean()),
        "comision_total": float(periods["comision_pagada"].sum()),
        "capital_final": float(nav_curve.iloc[-1]),
    }


def buy_and_hold_curve(symbol: str, start: str, end: str, initial_capital: float = 100_000.0,
                       commission_usd: float = broker_costs.STOCK_FEE_USD,
                       spread_bps: float = 10.0) -> pd.Series:
    """Curva NAV diaria de comprar `symbol` UNA VEZ al principio del rango
    (con su coste real de entrada, una sola vez) y mantenerlo sin volver a
    operar. Corrige directamente el fallo de V1, donde el benchmark SPY
    pagaba compra+venta completa cada rebalanceo igual que la propia
    estrategia, cuando comprar-y-mantener es justo lo que un benchmark
    pasivo hace."""
    calendar = xcals.get_calendar(_CALENDAR)
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    # A diferencia de una fecha de rebalanceo (que es una señal -> se compra
    # a la sesión SIGUIENTE), aquí `start` ya es la fecha de entrada exacta
    # que se quiere replicar (normalmente nav_curve.index[0] de `run()`) --
    # snap a la sesión válida en/después de `start`, sin saltarla.
    entry_session = calendar.date_to_session(start_ts, direction="next")
    exit_session = calendar.date_to_session(end_ts, direction="previous")
    history = identity.backtest_prices([symbol], start)[symbol]
    if (history.empty or entry_session not in history.index
            or pd.isna(history.loc[entry_session, "adj_close"]) or history.loc[entry_session, "adj_close"] <= 0):
        raise ValueError(f"Faltan precios ajustados de {symbol} en {entry_session.date()}.")
    price = float(history.loc[entry_session, "adj_close"])
    cash = float(initial_capital)
    shares: dict[str, float] = {}
    cash = _apply_trade(cash, shares, symbol, "BUY", initial_capital - commission_usd, price,
                        commission_usd, spread_bps)
    sessions = calendar.sessions_in_range(entry_session, exit_session)
    price_series = history["adj_close"].reindex(sessions).ffill().bfill()
    return cash + shares[symbol] * price_series
