"""Pure rules of the V1/V2 multifactor backtests: sampling, holding band, trade accounting and risk metrics.

Moved unchanged from ``multifactor_backtest`` (V1) and ``portfolio_backtest`` (V2), which
keep their historical names as aliases; only the risk-free rate is now a parameter.
"""
import random

import numpy as np
import pandas as pd

# Si una empresa lleva más de esto sin presentar NADA ante la SEC (ni un
# 10-Q trimestral), lo normal es que haya dejado de ser una "reporting
# company" viva — quiebra, exclusión, fusión. 450 días da margen (10-Q cada
# ~90 días + retraso) sin ser tan laxo como para dejar pasar casos reales.
MAX_DAYS_WITHOUT_FILING = 450

# Semilla fija: la lista de símbolos que devuelve universe.get_sp500_constituents_asof
# viene en orden ALFABÉTICO (comprobado con datos reales). Truncar con [:max_symbols]
# sobre esa lista no coge una muestra representativa: coge sistemáticamente las
# primeras letras del alfabeto y excluye TODO lo demás (con max_symbols=200 sobre
# ~500 empresas, se pierden enteras Coca-Cola/Pepsi/Procter/Visa/Walmart/Exxon...,
# cada trimestre, siempre). Un muestreo aleatorio con semilla fija es representativo
# y, al usar la misma semilla en cada llamada, sigue siendo reproducible.
SAMPLE_SEED = 42


def sample_symbols(symbols: list, max_symbols: int | None) -> list:
    if not max_symbols or len(symbols) <= max_symbols:
        return list(symbols)
    return random.Random(SAMPLE_SEED).sample(list(symbols), max_symbols)


def risk_metrics(returns: pd.Series, periods_per_year: float, years: float = None, *,
                 risk_free_rate: float) -> dict:
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
    rf = risk_free_rate
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


def apply_holding_buffer(previous_picks: list | None, ranked_pool: list, top_n: int,
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


def daily_risk_metrics(curve: pd.Series, *, risk_free_rate: float) -> dict:
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
    rf = risk_free_rate
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


def apply_trade(cash: float, shares: dict, symbol: str, side: str, notional: float,
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


def rebalance_to_weights(cash: float, shares: dict, target_weights: dict, entry_price: dict,
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
        cash = apply_trade(cash, shares, s, "SELL", notional, entry_price[s], commission_usd, spread_bps)
        if cash != before:
            traded_notional += notional
            trades_executed += 1

    for s in sorted(held):
        target_value = target_weights[s] * portfolio_value
        current_value = shares[s] * entry_price[s]
        delta = target_value - current_value
        side = "BUY" if delta > 0 else "SELL"
        before = cash
        cash = apply_trade(cash, shares, s, side, abs(delta), entry_price[s], commission_usd, spread_bps)
        if cash != before:
            traded_notional += abs(delta)
            trades_executed += 1

    for s in sorted(bought):
        target_value = target_weights[s] * portfolio_value
        before = cash
        cash = apply_trade(cash, shares, s, "BUY", target_value, entry_price[s], commission_usd, spread_bps)
        if cash != before:
            traded_notional += target_value
            trades_executed += 1

    turnover_pct = (traded_notional / portfolio_value * 100) if portfolio_value > 0 else 0.0
    commission_paid = trades_executed * commission_usd
    value_after = cash + sum(shares[s] * entry_price[s] for s in shares)
    total_cost = portfolio_value - value_after
    return {"cash": cash, "turnover_pct": turnover_pct,
            "comision_pagada": commission_paid,
            "spread_pagado": total_cost - commission_paid, "coste_total": total_cost,
            "held": held, "sold": sold, "bought": bought}


def rebalance(cash: float, shares: dict, picks: list, entry_price: dict, top_n: int,
              commission_usd: float, spread_bps: float) -> dict:
    """Rebalanceo equiponderado -- caso particular de `rebalance_to_weights`
    con `{s: 1/top_n for s in picks}`. Ver esa función para el detalle."""
    target_weights = {s: 1.0 / top_n for s in picks} if top_n else {}
    return rebalance_to_weights(cash, shares, target_weights, entry_price, commission_usd, spread_bps)


def settle_exits(cash: float, shares: dict, owners: dict, exits: dict, warnings: list) -> float:
    """Convierte en caja las posiciones que dejaron de cotizar en el periodo."""
    for symbol, info in exits.items():
        cash += shares.pop(symbol) * info["value"]
        owners.pop(symbol, None)
        warnings.append({"symbol": symbol, "fecha": info["date"].date().isoformat(), "estado": info["status"],
                         "estricto": info["strict"]})
    return cash
