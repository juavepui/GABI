"""V1 multifactor backtest over explicit inputs: periodic equal-weight rebalances of the point-in-time ranking.

Moved unchanged from ``multifactor_backtest`` (#132); data sources, calendar and clock now
come from ``BacktestMarket``. ``run`` receives ``period_returns`` so the frozen engines
that wrap ``multifactor_backtest._period_returns`` keep doing so.
"""

from collections.abc import Callable

import pandas as pd

from gabi.application.research.backtest_market import BacktestMarket
from gabi.domain.portfolio import backtest as rules
from gabi.domain.portfolio import rotation

PeriodReturns = Callable[..., dict]  # (symbols, as_of, months, cost_bps, held_symbols=None)


def required_symbols(market: BacktestMarket, start: str, end: str, months: int,
                     max_symbols: int | None = None) -> list[str]:
    current, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if current >= end_ts or not 1 <= months <= 12:
        raise ValueError("Intervalo o rebalanceo inválido.")
    symbols = set()
    while current + pd.DateOffset(months=months) <= end_ts:
        membership = market.membership(current.date().isoformat())
        if not membership["is_exact"]:
            raise ValueError(f"Sin composición histórica verificable para {current.date()}.")
        symbols.update(rules.sample_symbols(membership["symbols"], max_symbols))
        current += pd.DateOffset(months=months)
    if not symbols:
        raise ValueError("El intervalo no contiene ningún rebalanceo completo.")
    return sorted(symbols)


def period_returns(market: BacktestMarket, symbols: list[str], as_of: pd.Timestamp, months: int,
                   cost_bps: float, held_symbols: set = None) -> dict:
    """`held_symbols`: posiciones que YA se tenían en el periodo anterior y
    siguen igual en este — no pagan coste de entrada/salida, porque no se ha
    comprado ni vendido nada de verdad. Sin esto, un rebalanceo con banda de
    permanencia (menos turnover real) no vería ningún ahorro de coste en el
    resultado, porque se cobraría el mismo cost_bps a todo el mundo cada
    periodo, se toque la posición o no — precisamente el fallo que hacía que
    el experimento de reducción de turnover no midiera lo que decía medir."""
    calendar = market.calendar
    signal_session = calendar.date_to_session(as_of, direction="previous")
    entry = calendar.next_session(signal_session)
    exit_session = calendar.date_to_session(as_of + pd.DateOffset(months=months), direction="next")
    if exit_session > pd.Timestamp(market.today()):
        raise ValueError(f"El periodo iniciado en {as_of.date()} aún no tiene salida.")
    histories = market.prices(symbols + ["SPY"], as_of.date().isoformat())
    # SPY es un ETF, no una "reporting company" que pueda desaparecer y ver su
    # ticker reasignado a otra cosa — no necesita esta comprobación.
    # as_of=exit_session: point-in-time correcto -- si no se acota, un ticker
    # reciclado puede colar un filing FUTURO (de la empresa nueva que se
    # quedó el símbolo) y el guard nunca saltaría.
    last_filed = market.last_filings(symbols, exit_session.date().isoformat())
    missing = []
    recycled = []
    returns = {}
    held_symbols = held_symbols or set()
    factor_traded = (1 - cost_bps / 10000) ** 2
    exits = []
    for symbol in symbols + ["SPY"]:
        h = histories.get(symbol, pd.DataFrame())
        if (symbol != "SPY" and not h.empty and h.attrs.get("entity_id") and entry in h.index
                and exit_session not in h.index):
            # 2010-2015: la serie acreditada acaba antes de la salida.
            info = market.exit_value(h, h.attrs["entity_id"], entry, exit_session)
            if info["value"] is not None and h.loc[entry, "adj_close"] > 0:
                factor = 1.0 if symbol in (held_symbols or set()) else (1 - cost_bps / 10000) ** 2
                returns[symbol] = float(info["value"] / h.loc[entry, "adj_close"] * factor - 1)
                exits.append({"symbol": symbol, "estado": info["status"], "estricto": info["strict"]})
                continue
        if (h.empty or entry not in h.index or exit_session not in h.index
                or pd.isna(h.loc[entry, "adj_close"]) or pd.isna(h.loc[exit_session, "adj_close"])
                or h.loc[entry, "adj_close"] <= 0):
            missing.append(symbol)
            continue
        # SPY es la referencia pasiva (comprar y mantener), no una posición
        # que se rota cada rebalanceo -- cobrarle compra+venta completa cada
        # periodo, como al resto, infla artificialmente la ventaja de la
        # estrategia sobre su propio benchmark.
        factor = 1.0 if symbol == "SPY" or symbol in held_symbols else factor_traded
        if symbol != "SPY" and symbol in last_filed:
            gap_days = (exit_session - pd.Timestamp(last_filed[symbol])).days
            if gap_days > rules.MAX_DAYS_WITHOUT_FILING:
                # Sin ningún filing SEC en más de 450 días: lo más probable es
                # que la empresa original ya no exista como tal y que la
                # cotización que devuelve yfinance bajo este símbolo pertenezca
                # hoy a una empresa distinta que recicló el ticker (comprobado
                # con datos reales: "BBBY" devuelve cotización viva de 2026,
                # pero Bed Bath & Beyond quebró y fue excluida en 2023) — se
                # descarta en vez de atribuirle silenciosamente ese precio.
                recycled.append(symbol)
                continue
        returns[symbol] = float(h.loc[exit_session, "adj_close"] / h.loc[entry, "adj_close"] * factor - 1)
    if missing:
        raise ValueError(f"Faltan precios ajustados en entrada/salida ({entry.date()} / "
                         f"{exit_session.date()}): {', '.join(missing)}")
    if recycled:
        raise ValueError(f"Ticker probablemente reciclado (sin filings SEC recientes) en "
                         f"{exit_session.date()}: {', '.join(recycled)}")
    return {"end_date": exit_session.date().isoformat(),
            "portfolio_return": sum(returns[s] for s in symbols) / len(symbols),
            "benchmark_return": returns["SPY"], "exit_events": exits}


def run(market: BacktestMarket, period_returns: PeriodReturns, start: str, end: str, months: int = 3,
        top_n: int = 10, cost_bps: float = 10, min_coverage: float = .7, min_universe_coverage: float = .5,
        max_symbols: int | None = None, buffer_multiplier: float = 1.0,
        rotation_hurdle_points: float = 0.0) -> dict:
    """Backtest de rebalanceos periódicos. Un periodo sin cobertura suficiente
    (fundamentales/precios insuficientes para ese trimestre) se SALTA, no
    aborta todo el rango — así un solo trimestre problemático (frecuente en
    los años con menos cobertura SEC EDGAR) no impide ver el resto. Solo
    falla si NINGÚN periodo del rango es utilizable. `skipped` en el
    resultado lista qué se saltó y por qué.

    `min_universe_coverage=0.5` (antes 0.7): comprobado con datos reales que
    ~100 de los ~640 símbolos que hacen falta para cubrir 2016-2025 (≈16%)
    nunca resuelven CIK en SEC EDGAR — son empresas realmente deslistadas o
    adquiridas antes de 2022 (ABC, ANTM, ATVI, CELG, BBBY, RTN, UTX...), y
    `company_tickers.json` de la SEC solo mapea registrantes ACTIVOS hoy, no
    históricos. Eso limita la cobertura alcanzable de cualquier trimestre
    anterior a 2022 a un techo estructural de ~57-69% (no es un problema de
    calidad de esos periodos, es que ese es el máximo posible con esta
    fuente) — con el 0.7 anterior, TODO 2016-2021 se saltaba en silencio,
    incluido el crash de marzo de 2020, y un backtest lanzado desde la UI con
    los valores por defecto nunca lo mostraba salvo que se abriera el
    desplegable de periodos saltados. 0.5 recupera el rango completo (36/36
    trimestres verificado) sin dejar pasar periodos realmente vacíos.

    `buffer_multiplier` (>1.0) reduce el turnover con una banda de
    permanencia — ver `apply_holding_buffer`. Por defecto 1.0: sin banda,
    top-N estricto (comportamiento histórico de esta función)."""
    if not 1 <= months <= 12 or not 1 <= top_n <= 50 or cost_bps < 0:
        raise ValueError("Parámetros del backtest inválidos.")
    if not 0 < min_coverage <= 1 or not 0 < min_universe_coverage <= 1:
        raise ValueError("La cobertura debe estar entre 0 y 1.")
    if buffer_multiplier < 1.0:
        raise ValueError("buffer_multiplier debe ser >= 1.0.")
    if rotation_hurdle_points < 0:
        raise ValueError("rotation_hurdle_points debe ser >= 0.")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if start_ts >= end_ts or end_ts > pd.Timestamp(market.today()):
        raise ValueError("El intervalo debe terminar después del inicio y no superar hoy.")
    rows = []
    skipped = []
    quality_by_date = {}
    previous_picks: list[str] | None = None
    current = start_ts
    while current + pd.DateOffset(months=months) <= end_ts:
        as_of = current.date().isoformat()
        try:
            membership = market.membership(as_of)
            if not membership["is_exact"]:
                raise ValueError(membership["note"])
            symbols = rules.sample_symbols(membership["symbols"], max_symbols)
            ranked = market.ranking(as_of, symbols)
            quality_by_date[as_of] = market.quality(ranked)
            eligible = ranked[(ranked["composite_score"].notna())
                              & (ranked["score_coverage"] >= min_coverage)]
            if len(eligible) / len(symbols) < min_universe_coverage:
                raise ValueError(f"cobertura insuficiente del universo ({len(eligible)}/{len(symbols)})")
            ranked_pool = eligible.index.tolist()
            if rotation_hurdle_points > 0:
                scores = eligible["composite_score"].astype(float).to_dict()
                picks = rotation.select_with_score_hurdle(
                    previous_picks, ranked_pool, scores, top_n, rotation_hurdle_points)
            else:
                picks = rules.apply_holding_buffer(previous_picks, ranked_pool, top_n, buffer_multiplier)
            if len(picks) < top_n:
                raise ValueError(f"solo {len(picks)}/{top_n} candidatas con cobertura suficiente")
            held = set(picks) & set(previous_picks or [])
            outcome = period_returns(picks, current, months, cost_bps, held_symbols=held)
            universo_outcome = period_returns(eligible.index.tolist(), current, months, cost_bps)
            turnover_pct: float | None = (None if previous_picks is None
                                          else (top_n - len(held)) / top_n * 100)
            rows.append({"fecha": as_of, "hasta": outcome["end_date"],
                         "candidatas": ", ".join(picks), "cobertura universo": f"{len(eligible)}/{len(symbols)}",
                         "retorno": outcome["portfolio_return"], "spy": outcome["benchmark_return"],
                         "universo_ew": universo_outcome["portfolio_return"], "turnover_pct": turnover_pct})
            previous_picks = picks
        except (ValueError, RuntimeError) as exc:
            skipped.append({"fecha": as_of, "motivo": str(exc)})
        current += pd.DateOffset(months=months)
    if not rows:
        raise ValueError("Ningún periodo del rango tiene datos suficientes — "
                         f"se saltaron los {len(skipped)} periodos por falta de cobertura.")
    periods = pd.DataFrame(rows)
    periods["capital"] = (1 + periods["retorno"]).cumprod()
    periods["spy_capital"] = (1 + periods["spy"]).cumprod()
    periods["universo_capital"] = (1 + periods["universo_ew"]).cumprod()
    periods_per_year = 12 / months
    # Años de calendario REALES entre el inicio del primer periodo y el fin
    # del último — no len(periods)/periods_per_year, que se equivoca en
    # cuanto algún trimestre se salta por falta de cobertura (ver `skipped`):
    # comprimiría el mismo retorno total en menos años de los que realmente
    # pasaron e inflaría el anualizado y el Sharpe.
    calendar_years = (pd.Timestamp(periods["hasta"].iloc[-1]) - pd.Timestamp(periods["fecha"].iloc[0])).days / 365.25
    turnover_valid = periods["turnover_pct"].dropna()
    turnover_medio = float(turnover_valid.mean()) if not turnover_valid.empty else None

    def metrics(column: str) -> dict:
        return rules.risk_metrics(periods[column], periods_per_year, years=calendar_years,
                                  risk_free_rate=market.risk_free_rate)

    return {
        "data_quality": quality_by_date,
        "periods": periods, "skipped": skipped, "turnover_medio": turnover_medio,
        "rotation_hurdle_points": float(rotation_hurdle_points),
        "return": float(periods["capital"].iloc[-1] - 1),
        "spy_return": float(periods["spy_capital"].iloc[-1] - 1),
        "universo_ew_return": float(periods["universo_capital"].iloc[-1] - 1),
        "drawdown": float((periods["capital"] / periods["capital"].cummax() - 1).min()),
        "metrics": {"estrategia": metrics("retorno"), "universo_ew": metrics("universo_ew"), "spy": metrics("spy")},
    }


def daily_capital_curve(market: BacktestMarket, periods: pd.DataFrame) -> pd.Series:
    """Curva de capital DIARIA de la estrategia (no solo el capital en las
    fechas de rebalanceo que ya guarda `periods["capital"]`) — imprescindible
    para comparar Sharpe/Sortino/drawdown entre backtests con distinta
    frecuencia de rebalanceo (`months`).

    Sin esto, una caída y recuperación completa DENTRO de un periodo (ej. el
    crash de marzo de 2020 dentro de un periodo semestral o anual que termina
    recuperado) es invisible para el cálculo basado solo en el capital al
    cierre de cada periodo — y cuanto más espaciado el rebalanceo, más riesgo
    real queda escondido entre dos fotos. Con la curva diaria, Sharpe/Sortino/
    drawdown de trimestral, semestral y anual pasan a ser comparables de verdad.

    El retorno diario dentro de cada periodo es el de la cesta equiponderada
    SIN coste (los precios tal cual) — el coste real de ese periodo (ya
    calculado en `periods["retorno"]`, con el descuento por reciclaje/held_symbols
    ya aplicado) se incorpora como un único factor de escala sobre todo el
    tramo, para que el valor final del periodo coincida exactamente con el
    retorno ya validado, sin inventarse cuándo dentro del periodo se paga el
    coste (day trading real de eso no lo sabemos, y no cambia la forma de la
    curva lo suficiente como para que importe para el drawdown)."""
    calendar = market.calendar
    running_capital = 1.0
    pieces = []
    for _, row in periods.iterrows():
        symbols = [s.strip() for s in row["candidatas"].split(",") if s.strip()]
        if not symbols:
            continue
        signal_session = calendar.date_to_session(pd.Timestamp(row["fecha"]), direction="previous")
        entry = calendar.next_session(signal_session)
        exit_session = pd.Timestamp(row["hasta"])
        histories = market.prices(symbols, str(row["fecha"])[:10])
        series = {}
        for symbol in symbols:
            h = histories.get(symbol)
            if h is None or h.empty or "adj_close" not in h:
                continue
            s = h["adj_close"].dropna()
            s = s[(s.index >= entry) & (s.index <= exit_session)]
            if not s.empty and s.iloc[0] > 0:
                series[symbol] = s / s.iloc[0]
        if not series:
            continue
        basket = pd.concat(series, axis=1).mean(axis=1, skipna=True)
        raw_end_return = float(basket.iloc[-1] - 1)
        actual_return = float(row["retorno"])
        scale = (1 + actual_return) / (1 + raw_end_return) if (1 + raw_end_return) != 0 else 1.0
        period_curve = basket * scale * running_capital
        pieces.append(period_curve)
        running_capital = float(period_curve.iloc[-1])
    if not pieces:
        return pd.Series(dtype=float)
    return pd.concat(pieces).sort_index()


def daily_benchmark_curve(market: BacktestMarket, periods: pd.DataFrame, return_column: str = "spy",
                          symbol: str = "SPY") -> pd.Series:
    """Curva de capital DIARIA de un benchmark comprado-y-mantenido (por
    defecto SPY) sobre el MISMO rango de fechas y con la MISMA reconstrucción
    que `daily_capital_curve` usa para la estrategia — imprescindible para
    comparar max_drawdown con el índice de forma justa: si se compara el
    drawdown diario de la estrategia contra el drawdown por snapshots del
    benchmark (o viceversa), la diferencia puede venir solo de la metodología,
    no de un riesgo real distinto. Reutiliza `daily_capital_curve` construyendo
    una tabla de periodos "de mentira" con una sola candidata (el símbolo del
    benchmark) y el retorno de ese periodo ya calculado en `periods[return_column]`."""
    pseudo = periods[["fecha", "hasta"]].copy()
    pseudo["candidatas"] = symbol
    pseudo["retorno"] = periods[return_column]
    return daily_capital_curve(market, pseudo)
