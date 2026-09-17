"""Backtest multifactor con rebalanceos periódicos, reconstruyendo el ranking
point-in-time en cada fecha con los datos de SEC EDGAR y los precios
ajustados ya cacheados."""
import random
from datetime import date

import numpy as np
import pandas as pd
import exchange_calendars as xcals

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
                    cost_bps: float) -> dict:
    calendar = xcals.get_calendar("XNYS")
    signal_session = calendar.date_to_session(as_of, direction="previous")
    entry = calendar.next_session(signal_session)
    exit_session = calendar.date_to_session(as_of + pd.DateOffset(months=months), direction="next")
    if exit_session > pd.Timestamp(date.today()):
        raise ValueError(f"El periodo iniciado en {as_of.date()} aún no tiene salida.")
    histories = storage.get_prices_multi(symbols + ["SPY"])
    # SPY es un ETF, no una "reporting company" que pueda desaparecer y ver su
    # ticker reasignado a otra cosa — no necesita esta comprobación.
    last_filed = edgar.get_last_filed_dates(symbols)
    missing = []
    recycled = []
    returns = {}
    factor = (1 - cost_bps / 10000) ** 2
    for symbol in symbols + ["SPY"]:
        h = histories.get(symbol, pd.DataFrame())
        if (h.empty or entry not in h.index or exit_session not in h.index
                or pd.isna(h.loc[entry, "adj_close"]) or pd.isna(h.loc[exit_session, "adj_close"])
                or h.loc[entry, "adj_close"] <= 0):
            missing.append(symbol)
            continue
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


def _risk_metrics(returns: pd.Series, periods_per_year: float) -> dict:
    """Sharpe, Sortino, volatilidad anualizada y máximo drawdown sobre una
    serie de retornos por periodo (no diarios) — mismas fórmulas que
    risk.py pero anualizando por nº de rebalanceos/año en vez de por 252
    sesiones, y con la misma tasa libre de riesgo (config.RISK_FREE_RATE)
    que usa el resto de la app para que Sharpe/Sortino sean comparables
    entre pantallas."""
    n = len(returns)
    if n == 0:
        return {"anualizado": None, "vol_anualizada": None, "sharpe": None,
                "sortino": None, "max_drawdown": None}
    rf = config.RISK_FREE_RATE
    capital = (1 + returns).cumprod()
    total_return = float(capital.iloc[-1] - 1)
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


def run(start: str, end: str, months: int = 3, top_n: int = 10,
        cost_bps: float = 10, min_coverage: float = .7, min_universe_coverage: float = .7,
        max_symbols: int | None = None) -> dict:
    """Backtest de rebalanceos periódicos. Un periodo sin cobertura suficiente
    (fundamentales/precios insuficientes para ese trimestre) se SALTA, no
    aborta todo el rango — así un solo trimestre problemático (frecuente en
    los años con menos cobertura SEC EDGAR) no impide ver el resto. Solo
    falla si NINGÚN periodo del rango es utilizable. `skipped` en el
    resultado lista qué se saltó y por qué."""
    if not 1 <= months <= 12 or not 1 <= top_n <= 50 or cost_bps < 0:
        raise ValueError("Parámetros del backtest inválidos.")
    if not 0 < min_coverage <= 1 or not 0 < min_universe_coverage <= 1:
        raise ValueError("La cobertura debe estar entre 0 y 1.")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if start_ts >= end_ts or end_ts > pd.Timestamp(date.today()):
        raise ValueError("El intervalo debe terminar después del inicio y no superar hoy.")
    rows = []
    skipped = []
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
            picks = eligible.head(top_n).index.tolist()
            if len(picks) < top_n:
                raise ValueError(f"solo {len(picks)}/{top_n} candidatas con cobertura suficiente")
            outcome = _period_returns(picks, current, months, cost_bps)
            universo_outcome = _period_returns(eligible.index.tolist(), current, months, cost_bps)
            rows.append({"fecha": as_of, "hasta": outcome["end_date"],
                         "candidatas": ", ".join(picks), "cobertura universo": f"{len(eligible)}/{len(symbols)}",
                         "retorno": outcome["portfolio_return"], "spy": outcome["benchmark_return"],
                         "universo_ew": universo_outcome["portfolio_return"]})
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
    return {
        "periods": periods, "skipped": skipped,
        "return": float(periods["capital"].iloc[-1] - 1),
        "spy_return": float(periods["spy_capital"].iloc[-1] - 1),
        "universo_ew_return": float(periods["universo_capital"].iloc[-1] - 1),
        "drawdown": float((periods["capital"] / periods["capital"].cummax() - 1).min()),
        "metrics": {
            "estrategia": _risk_metrics(periods["retorno"], periods_per_year),
            "universo_ew": _risk_metrics(periods["universo_ew"], periods_per_year),
            "spy": _risk_metrics(periods["spy"], periods_per_year),
        },
    }
