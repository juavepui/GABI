"""V2 multifactor backtest over explicit inputs: real share/cash accounting and a genuine daily NAV.

Moved unchanged from ``portfolio_backtest`` (#132); data sources, calendar and clock now
come from ``BacktestMarket``. ``run`` receives ``rebalance`` and ``daily_segment`` so the
frozen engines that wrap ``portfolio_backtest._rebalance``/``_daily_segment`` keep doing so.
"""

from collections.abc import Callable

import pandas as pd

from gabi.application.research.backtest_market import BacktestMarket, NoCoveredPeriods
from gabi.domain.portfolio import backtest as rules
from gabi.domain.portfolio import broker_costs, rotation

VALID_MODES = ("validation", "fast_dev")


def daily_segment(market: BacktestMarket, cash: float, shares: dict, entry_session: pd.Timestamp,
                  exit_session: pd.Timestamp, sessions: pd.DatetimeIndex, *, owners: dict | None = None) -> pd.Series:
    """Valora caja + Σ(acciones × adj_close del día) sesión a sesión --
    mismo patrón que `sim_portfolios.portfolio_history()`. Se calcula
    SIEMPRE, incluso si el rebalanceo de ese periodo se saltó por falta de
    cobertura: la cartera sigue flotando con lo que ya tenía (a diferencia
    de V1, donde un periodo saltado deja un hueco en la curva)."""
    segment = pd.Series(cash, index=sessions, dtype=float)
    if not shares:
        return segment
    histories = market.prices(list(shares.keys()), entry_session.date().isoformat(), owners)
    exits = historical_exits(market, histories, shares, owners, entry_session, exit_session)
    for symbol, qty in shares.items():
        h = histories.get(symbol, pd.DataFrame())
        if symbol in exits:
            # La serie acreditada termina antes de la salida: hasta su último
            # día se valora a mercado y después al valor de salida (evento
            # terminal o último precio marcado como no estricto).
            exit_info = exits[symbol]
            prices = h["adj_close"].reindex(sessions)
            before = prices.index <= exit_info["date"]
            if prices[before].isna().any():
                raise ValueError(f"Missing attributed prices for held entity {(owners or {}).get(symbol)}")
            prices[~before] = exit_info["value"]
            segment = segment.add(qty * prices, fill_value=0.0)
            continue
        if owners and owners.get(symbol):
            if h.empty or h["adj_close"].reindex(sessions).isna().any():
                raise ValueError(f"Missing attributed prices for held entity {owners[symbol]}")
        if h.empty or "adj_close" not in h:
            continue
        price_series = h["adj_close"].reindex(sessions).ffill().bfill()
        segment = segment.add(qty * price_series.fillna(0.0), fill_value=0.0)
    return segment


def historical_exits(market: BacktestMarket, histories: dict, shares: dict, owners: dict | None,
                     entry_session: pd.Timestamp, exit_session: pd.Timestamp) -> dict:
    """Posiciones 2010-2015 cuya serie acreditada acaba antes de ``exit_session``."""
    exits = {}
    for symbol in shares:
        owner = (owners or {}).get(symbol)
        h = histories.get(symbol, pd.DataFrame())
        if not owner or h.empty or h.attrs.get("entity_id") != owner or exit_session in h.index:
            continue
        info = market.exit_value(h, owner, entry_session, exit_session)
        if info["value"] is not None and info["date"] is not None and info["date"] < exit_session:
            exits[symbol] = info
    return exits


def run(market: BacktestMarket, rebalance: Callable[..., dict], daily_segment: Callable[..., pd.Series],
        start: str, end: str, months: int = 3, top_n: int = 20, max_symbols: int | None = None,
        mode: str = "validation", initial_capital: float = 100_000.0,
        commission_usd: float = broker_costs.STOCK_FEE_USD,
        spread_bps: float = 10.0, min_coverage: float = .7, min_universe_coverage: float = .5,
        rotation_hurdle_points: float = 0.0) -> dict:
    """Backtest V2 con contabilidad real de cartera. Mismo bucle de
    reconstrucción point-in-time que el backtest V1
    (universo histórico + ranking SEC EDGAR a fecha), pero el resultado de
    cada rebalanceo es una operación real sobre acciones/caja (`rebalance`)
    en vez de un retorno porcentual agregado, y la curva de capital es un
    walk-forward diario real (`daily_segment`), no una reconstrucción
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
    if rotation_hurdle_points < 0:
        raise ValueError("rotation_hurdle_points debe ser >= 0.")
    if initial_capital <= commission_usd:
        raise ValueError("initial_capital debe ser mayor que commission_usd.")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if start_ts >= end_ts or end_ts > pd.Timestamp(market.today()):
        raise ValueError("El intervalo debe terminar después del inicio y no superar hoy.")

    calendar = market.calendar
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
    exit_warnings: list[dict] = []

    for i in range(len(boundaries) - 1):
        as_of = boundaries[i]
        as_of_str = as_of.date().isoformat()
        signal_session = calendar.date_to_session(as_of, direction="previous")
        entry_session = calendar.next_session(signal_session)
        exit_session = calendar.date_to_session(boundaries[i + 1], direction="next")

        try:
            if exit_session > pd.Timestamp(market.today()):
                raise ValueError(f"El periodo iniciado en {as_of.date()} aún no tiene salida.")
            membership = market.membership(as_of_str)
            if not membership["is_exact"]:
                raise ValueError(membership["note"])
            symbols = rules.sample_symbols(membership["symbols"], max_symbols)
            ranked = market.ranking(as_of_str, symbols)
            quality_by_date[as_of_str] = market.quality(ranked)
            eligible = ranked[(ranked["composite_score"].notna())
                              & (ranked["score_coverage"] >= min_coverage)]
            if len(eligible) / len(symbols) < min_universe_coverage:
                raise ValueError(f"cobertura insuficiente del universo ({len(eligible)}/{len(symbols)})")
            ranked_pool = eligible.index.tolist()
            scores = eligible["composite_score"].astype(float).to_dict()
            picks = rotation.select_with_score_hurdle(
                list(shares), ranked_pool, scores, top_n, rotation_hurdle_points)
            if len(picks) < top_n:
                raise ValueError(f"solo {len(picks)}/{top_n} candidatas con cobertura suficiente")

            needed = sorted(set(shares.keys()) | set(picks))
            for symbol in needed:
                owner = market.owner(symbol, as_of_str)
                if symbol in shares and owners.get(symbol) and owner and owners[symbol] != owner:
                    raise ValueError(f"Ticker reassigned while holding {symbol}")
                if owner and (symbol not in owners or symbol not in shares):
                    owners[symbol] = owner
            histories = market.prices(needed, as_of_str, owners)
            last_filed = market.last_filings(needed, exit_session.date().isoformat())
            missing, recycled, entry_price = [], [], {}
            for s in needed:
                h = histories.get(s, pd.DataFrame())
                if (h.empty or entry_session not in h.index or pd.isna(h.loc[entry_session, "adj_close"])
                        or h.loc[entry_session, "adj_close"] <= 0):
                    missing.append(s)
                    continue
                if s in last_filed:
                    gap_days = (exit_session - pd.Timestamp(last_filed[s])).days
                    if gap_days > rules.MAX_DAYS_WITHOUT_FILING:
                        recycled.append(s)
                        continue
                entry_price[s] = float(h.loc[entry_session, "adj_close"])
            if missing:
                raise ValueError(f"Faltan precios ajustados en entrada ({entry_session.date()}): "
                                 f"{', '.join(missing)}")
            if recycled:
                raise ValueError(f"Ticker probablemente reciclado en {exit_session.date()}: "
                                 f"{', '.join(recycled)}")

            result = rebalance(cash, shares, picks, entry_price, top_n, commission_usd, spread_bps)
            cash = result["cash"]
            rows.append({
                "fecha": as_of_str, "hasta": exit_session.date().isoformat(),
                "held": ", ".join(sorted(result["held"])), "sold": ", ".join(sorted(result["sold"])),
                "bought": ", ".join(sorted(result["bought"])), "turnover_pct": result["turnover_pct"],
                "comision_pagada": result["comision_pagada"],
                "spread_pagado": result["spread_pagado"], "coste_total": result["coste_total"],
            })
        except (ValueError, RuntimeError) as exc:
            skipped.append({"fecha": as_of_str, "motivo": str(exc)})

        sessions = calendar.sessions_in_range(entry_session, exit_session)
        nav_pieces.append(daily_segment(cash, shares, entry_session, exit_session, sessions, owners=owners))
        if shares and owners:
            held_histories = market.prices(list(shares), entry_session.date().isoformat(), owners)
            cash = rules.settle_exits(cash, shares, owners,
                                      historical_exits(market, held_histories, shares, owners,
                                                       entry_session, exit_session),
                                      exit_warnings)

    if not rows:
        raise NoCoveredPeriods("Ningún periodo del rango tiene datos suficientes — "
                         f"se saltaron los {len(skipped)} periodos por falta de cobertura.")

    nav_curve = pd.concat(nav_pieces).sort_index()
    nav_curve = nav_curve[~nav_curve.index.duplicated(keep="last")]
    periods = pd.DataFrame(rows)
    nav_curve_spy = buy_and_hold_curve(market, "SPY", nav_curve.index[0].date().isoformat(),
                                       nav_curve.index[-1].date().isoformat(),
                                       initial_capital=initial_capital,
                                       commission_usd=commission_usd, spread_bps=spread_bps)

    return {
        "data_quality": quality_by_date,
        "mode": mode, "periods": periods, "skipped": skipped,
        # 2010-2015: salidas por evento terminal; `estricto=False` = último
        # precio sin evento confirmado, a revisar antes de citar el resultado.
        "exit_events": exit_warnings,
        "strict_result": all(item["estricto"] for item in exit_warnings),
        "rotation_hurdle_points": float(rotation_hurdle_points),
        "nav_curve": nav_curve, "nav_curve_spy": nav_curve_spy,
        "turnover_medio": float(periods["turnover_pct"].mean()),
        "comision_total": float(periods["comision_pagada"].sum()),
        "spread_total": float(periods["spread_pagado"].sum()),
        "coste_total": float(periods["coste_total"].sum()),
        "initial_capital": float(initial_capital),
        "capital_final": float(nav_curve.iloc[-1]),
    }


def buy_and_hold_curve(market: BacktestMarket, symbol: str, start: str, end: str,
                       initial_capital: float = 100_000.0, commission_usd: float = broker_costs.STOCK_FEE_USD,
                       spread_bps: float = 10.0) -> pd.Series:
    """Curva NAV diaria de comprar `symbol` UNA VEZ al principio del rango
    (con su coste real de entrada, una sola vez) y mantenerlo sin volver a
    operar. Corrige directamente el fallo de V1, donde el benchmark SPY
    pagaba compra+venta completa cada rebalanceo igual que la propia
    estrategia, cuando comprar-y-mantener es justo lo que un benchmark
    pasivo hace."""
    calendar = market.calendar
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    # A diferencia de una fecha de rebalanceo (que es una señal -> se compra
    # a la sesión SIGUIENTE), aquí `start` ya es la fecha de entrada exacta
    # que se quiere replicar (normalmente nav_curve.index[0] de `run()`) --
    # snap a la sesión válida en/después de `start`, sin saltarla.
    entry_session = calendar.date_to_session(start_ts, direction="next")
    exit_session = calendar.date_to_session(end_ts, direction="previous")
    history = market.prices([symbol], start)[symbol]
    if (history.empty or entry_session not in history.index
            or pd.isna(history.loc[entry_session, "adj_close"]) or history.loc[entry_session, "adj_close"] <= 0):
        raise ValueError(f"Faltan precios ajustados de {symbol} en {entry_session.date()}.")
    price = float(history.loc[entry_session, "adj_close"])
    cash = float(initial_capital)
    shares: dict[str, float] = {}
    cash = rules.apply_trade(cash, shares, symbol, "BUY", initial_capital - commission_usd, price,
                             commission_usd, spread_bps)
    sessions = calendar.sessions_in_range(entry_session, exit_session)
    price_series = history["adj_close"].reindex(sessions).ffill().bfill()
    return cash + shares[symbol] * price_series
