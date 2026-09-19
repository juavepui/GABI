"""Backtest multifactor con rebalanceos periódicos, reconstruyendo el ranking
point-in-time en cada fecha con los datos de SEC EDGAR y los precios
ajustados ya cacheados."""
import random
from datetime import date

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from . import config, edgar, screener_asof, storage, universe

# Si una empresa lleva más de esto sin presentar NADA ante la SEC (ni un
# 10-Q trimestral), lo normal es que haya dejado de ser una "reporting
# company" viva — quiebra, exclusión, fusión. 450 días da margen (10-Q cada
# ~90 días + retraso) sin ser tan laxo como para dejar pasar casos reales.
_MAX_DAYS_WITHOUT_FILING = 450

# Semilla fija: la lista de símbolos que devuelve universe.get_sp500_constituents_asof
# viene en orden ALFABÉTICO (comprobado con datos reales). Truncar con [:max_symbols]
# sobre esa lista no coge una muestra representativa: coge sistemáticamente las
# primeras letras del alfabeto y excluye TODO lo demás (con max_symbols=200 sobre
# ~500 empresas, se pierden enteras Coca-Cola/Pepsi/Procter/Visa/Walmart/Exxon...,
# cada trimestre, siempre). Un muestreo aleatorio con semilla fija es representativo
# y, al usar la misma semilla en cada llamada, sigue siendo reproducible.
_SAMPLE_SEED = 42


def _sample_symbols(symbols: list, max_symbols: int | None) -> list:
    if not max_symbols or len(symbols) <= max_symbols:
        return list(symbols)
    return random.Random(_SAMPLE_SEED).sample(list(symbols), max_symbols)


def required_symbols(start: str, end: str, months: int,
                     max_symbols: int | None = None) -> list[str]:
    current, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if current >= end_ts or not 1 <= months <= 12:
        raise ValueError("Intervalo o rebalanceo inválido.")
    symbols = set()
    while current + pd.DateOffset(months=months) <= end_ts:
        membership = universe.get_sp500_constituents_asof(current.date().isoformat())
        if not membership["is_exact"]:
            raise ValueError(f"Sin composición histórica verificable para {current.date()}.")
        symbols.update(_sample_symbols(membership["symbols"], max_symbols))
        current += pd.DateOffset(months=months)
    if not symbols:
        raise ValueError("El intervalo no contiene ningún rebalanceo completo.")
    return sorted(symbols)


def _period_returns(symbols: list[str], as_of: pd.Timestamp, months: int,
                    cost_bps: float, held_symbols: set = None) -> dict:
    """`held_symbols`: posiciones que YA se tenían en el periodo anterior y
    siguen igual en este — no pagan coste de entrada/salida, porque no se ha
    comprado ni vendido nada de verdad. Sin esto, un rebalanceo con banda de
    permanencia (menos turnover real) no vería ningún ahorro de coste en el
    resultado, porque se cobraría el mismo cost_bps a todo el mundo cada
    periodo, se toque la posición o no — precisamente el fallo que hacía que
    el experimento de reducción de turnover no midiera lo que decía medir."""
    calendar = xcals.get_calendar("XNYS")
    signal_session = calendar.date_to_session(as_of, direction="previous")
    entry = calendar.next_session(signal_session)
    exit_session = calendar.date_to_session(as_of + pd.DateOffset(months=months), direction="next")
    if exit_session > pd.Timestamp(date.today()):
        raise ValueError(f"El periodo iniciado en {as_of.date()} aún no tiene salida.")
    histories = storage.get_prices_multi(symbols + ["SPY"])
    # SPY es un ETF, no una "reporting company" que pueda desaparecer y ver su
    # ticker reasignado a otra cosa — no necesita esta comprobación.
    # as_of=exit_session: point-in-time correcto -- si no se acota, un ticker
    # reciclado puede colar un filing FUTURO (de la empresa nueva que se
    # quedó el símbolo) y el guard nunca saltaría.
    last_filed = edgar.get_last_filed_dates(symbols, as_of=exit_session.date().isoformat())
    missing = []
    recycled = []
    returns = {}
    held_symbols = held_symbols or set()
    factor_traded = (1 - cost_bps / 10000) ** 2
    for symbol in symbols + ["SPY"]:
        h = histories.get(symbol, pd.DataFrame())
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
            if gap_days > _MAX_DAYS_WITHOUT_FILING:
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
            "benchmark_return": returns["SPY"]}


def _risk_metrics(returns: pd.Series, periods_per_year: float, years: float = None) -> dict:
    """Sharpe, Sortino, volatilidad anualizada y máximo drawdown sobre una
    serie de retornos por periodo (no diarios) — mismas fórmulas que
    risk.py pero anualizando por nº de rebalanceos/año en vez de por 252
    sesiones, y con la misma tasa libre de riesgo (config.RISK_FREE_RATE)
    que usa el resto de la app para que Sharpe/Sortino sean comparables
    entre pantallas.

    `years`: años de calendario REALES transcurridos entre el inicio del
    primer periodo y el final del último — si se omite, se aproxima con
    `len(returns) / periods_per_year`, pero esa aproximación **se equivoca
    en cuanto se salta algún periodo** (`skipped` en `run()`): el retorno
    total se comprimiría en menos años de los que realmente pasaron y el
    anualizado/Sharpe saldrían inflados. Pásalo siempre que se conozcan las
    fechas reales de inicio y fin (ver `run()`)."""
    n = len(returns)
    if n == 0:
        return {"anualizado": None, "vol_anualizada": None, "sharpe": None,
                "sortino": None, "max_drawdown": None}
    rf = config.RISK_FREE_RATE
    capital = (1 + returns).cumprod()
    total_return = float(capital.iloc[-1] - 1)
    if years is None:
        years = n / periods_per_year
    ann_return = (1 + total_return) ** (1 / years) - 1 if (1 + total_return) > 0 and years > 0 else None
    ann_vol = float(returns.std(ddof=1) * np.sqrt(periods_per_year)) if n > 1 else None
    sharpe = (ann_return - rf) / ann_vol if ann_return is not None and ann_vol else None
    period_target = (1 + rf) ** (1 / periods_per_year) - 1
    shortfall = np.minimum(returns - period_target, 0)
    downside_dev = float(np.sqrt(np.mean(np.square(shortfall))) * np.sqrt(periods_per_year))
    sortino = (ann_return - rf) / downside_dev if ann_return is not None and downside_dev else None
    max_dd = float((capital / capital.cummax() - 1).min())
    return {"anualizado": ann_return, "vol_anualizada": ann_vol, "sharpe": sharpe,
            "sortino": sortino, "max_drawdown": max_dd}


def _apply_holding_buffer(previous_picks: list, ranked_pool: list, top_n: int,
                          buffer_multiplier: float) -> list:
    """Banda de permanencia para reducir turnover: una posición ya en cartera
    no se vende solo por perder el primer puesto — se mantiene mientras siga
    dentro de una banda más ancha (`top_n * buffer_multiplier`, ej. las 30
    mejores en vez de exigir estar entre las 20 mejores si `top_n=20` y
    `buffer_multiplier=1.5`). Solo se incorporan candidatas nuevas para
    ocupar los huecos que dejen las que sí salen de la banda.
    `buffer_multiplier<=1.0` desactiva la banda: top-N estricto cada
    rebalanceo, el comportamiento de siempre."""
    if buffer_multiplier <= 1.0 or not previous_picks:
        return ranked_pool[:top_n]
    band_size = max(top_n, int(round(top_n * buffer_multiplier)))
    exit_band = set(ranked_pool[:band_size])
    kept = [s for s in previous_picks if s in exit_band]
    if len(kept) > top_n:
        rank_index = {s: i for i, s in enumerate(ranked_pool)}
        kept = sorted(kept, key=lambda s: rank_index.get(s, len(ranked_pool)))[:top_n]
    picks = list(kept)
    for s in ranked_pool:
        if len(picks) >= top_n:
            break
        if s not in picks:
            picks.append(s)
    return picks


def run(start: str, end: str, months: int = 3, top_n: int = 10,
        cost_bps: float = 10, min_coverage: float = .7, min_universe_coverage: float = .5,
        max_symbols: int | None = None, buffer_multiplier: float = 1.0) -> dict:
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
    permanencia — ver `_apply_holding_buffer`. Por defecto 1.0: sin banda,
    top-N estricto (comportamiento histórico de esta función)."""
    if not 1 <= months <= 12 or not 1 <= top_n <= 50 or cost_bps < 0:
        raise ValueError("Parámetros del backtest inválidos.")
    if not 0 < min_coverage <= 1 or not 0 < min_universe_coverage <= 1:
        raise ValueError("La cobertura debe estar entre 0 y 1.")
    if buffer_multiplier < 1.0:
        raise ValueError("buffer_multiplier debe ser >= 1.0.")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if start_ts >= end_ts or end_ts > pd.Timestamp(date.today()):
        raise ValueError("El intervalo debe terminar después del inicio y no superar hoy.")
    rows = []
    skipped = []
    previous_picks = None
    current = start_ts
    while current + pd.DateOffset(months=months) <= end_ts:
        as_of = current.date().isoformat()
        try:
            membership = universe.get_sp500_constituents_asof(as_of)
            if not membership["is_exact"]:
                raise ValueError(membership["note"])
            symbols = _sample_symbols(membership["symbols"], max_symbols)
            ranked = screener_asof.build_ranking_as_of(as_of, symbols=symbols)["table"]
            eligible = ranked[(ranked["composite_score"].notna())
                              & (ranked["score_coverage"] >= min_coverage)]
            if len(eligible) / len(symbols) < min_universe_coverage:
                raise ValueError(f"cobertura insuficiente del universo ({len(eligible)}/{len(symbols)})")
            ranked_pool = eligible.index.tolist()
            picks = _apply_holding_buffer(previous_picks, ranked_pool, top_n, buffer_multiplier)
            if len(picks) < top_n:
                raise ValueError(f"solo {len(picks)}/{top_n} candidatas con cobertura suficiente")
            held = set(picks) & set(previous_picks or [])
            outcome = _period_returns(picks, current, months, cost_bps, held_symbols=held)
            universo_outcome = _period_returns(eligible.index.tolist(), current, months, cost_bps)
            turnover_pct = (None if previous_picks is None
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
    return {
        "periods": periods, "skipped": skipped, "turnover_medio": turnover_medio,
        "return": float(periods["capital"].iloc[-1] - 1),
        "spy_return": float(periods["spy_capital"].iloc[-1] - 1),
        "universo_ew_return": float(periods["universo_capital"].iloc[-1] - 1),
        "drawdown": float((periods["capital"] / periods["capital"].cummax() - 1).min()),
        "metrics": {
            "estrategia": _risk_metrics(periods["retorno"], periods_per_year, years=calendar_years),
            "universo_ew": _risk_metrics(periods["universo_ew"], periods_per_year, years=calendar_years),
            "spy": _risk_metrics(periods["spy"], periods_per_year, years=calendar_years),
        },
    }


def daily_capital_curve(periods: pd.DataFrame) -> pd.Series:
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
    calendar = xcals.get_calendar("XNYS")
    running_capital = 1.0
    pieces = []
    for _, row in periods.iterrows():
        symbols = [s.strip() for s in row["candidatas"].split(",") if s.strip()]
        if not symbols:
            continue
        signal_session = calendar.date_to_session(pd.Timestamp(row["fecha"]), direction="previous")
        entry = calendar.next_session(signal_session)
        exit_session = pd.Timestamp(row["hasta"])
        histories = storage.get_prices_multi(symbols)
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


def daily_benchmark_curve(periods: pd.DataFrame, return_column: str = "spy",
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
    return daily_capital_curve(pseudo)


def sharpe_standard_error(sharpe: float, years: float) -> float:
    """Error estándar aproximado de un Sharpe ratio estimado sobre `years`
    años de datos (fórmula estándar para retornos ~ i.i.d., ver Lo 2002):
    SE ≈ sqrt((1 + sharpe²/2) / years).

    Con los ~9 años de historia disponibles en estos backtests, el SE ronda
    ±0.35-0.37 — una diferencia de Sharpe entre dos variantes (ej. distinta
    frecuencia de rebalanceo, o con/sin banda de permanencia) por debajo de
    eso NO se puede distinguir del ruido de muestreo, aunque una parezca
    claramente mejor en la tabla. Con solo ~9 realizaciones anuales de
    historia de mercado, la incertidumbre de muestreo es grande — hace falta
    usarlo SIEMPRE que se compare el Sharpe de dos variantes sobre el mismo
    rango de fechas, para no convertir ruido en una conclusión."""
    if years <= 0:
        raise ValueError("years debe ser positivo.")
    return float(np.sqrt((1 + sharpe ** 2 / 2) / years))


def daily_risk_metrics(curve: pd.Series) -> dict:
    """Sharpe, Sortino, volatilidad y máximo drawdown sobre una curva de
    capital DIARIA — anualiza siempre con la convención estándar de 252
    sesiones, así que es comparable entre backtests con cualquier frecuencia
    de rebalanceo (a diferencia de `_risk_metrics`, pensada para comparar
    variantes con la MISMA frecuencia entre sí)."""
    if curve.empty or len(curve) < 2:
        return {"anualizado": None, "vol_anualizada": None, "sharpe": None,
                "sortino": None, "max_drawdown": None}
    returns = curve.pct_change().dropna()
    if returns.empty:
        return {"anualizado": None, "vol_anualizada": None, "sharpe": None,
                "sortino": None, "max_drawdown": None}
    rf = config.RISK_FREE_RATE
    total_return = float(curve.iloc[-1] / curve.iloc[0] - 1)
    years = len(curve) / 252
    ann_return = (1 + total_return) ** (1 / years) - 1 if (1 + total_return) > 0 and years > 0 else None
    ann_vol = float(returns.std(ddof=1) * np.sqrt(252))
    sharpe = (ann_return - rf) / ann_vol if ann_return is not None and ann_vol else None
    daily_target = (1 + rf) ** (1 / 252) - 1
    shortfall = np.minimum(returns - daily_target, 0)
    downside_dev = float(np.sqrt(np.mean(np.square(shortfall))) * np.sqrt(252))
    sortino = (ann_return - rf) / downside_dev if ann_return is not None and downside_dev else None
    max_dd = float((curve / curve.cummax() - 1).min())
    return {"anualizado": ann_return, "vol_anualizada": ann_vol, "sharpe": sharpe,
            "sortino": sortino, "max_drawdown": max_dd}
