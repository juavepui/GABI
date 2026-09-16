"""Backtest multifactor con rebalanceos periódicos, reconstruyendo el ranking
point-in-time en cada fecha con los datos de SEC EDGAR y los precios
ajustados ya cacheados."""
from datetime import date

import pandas as pd
import exchange_calendars as xcals

from . import screener_asof, storage, universe


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
        symbols.update(membership["symbols"][:max_symbols] if max_symbols else membership["symbols"])
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
    missing = []
    returns = {}
    factor = (1 - cost_bps / 10000) ** 2
    for symbol in symbols + ["SPY"]:
        h = histories.get(symbol, pd.DataFrame())
        if (h.empty or entry not in h.index or exit_session not in h.index
                or pd.isna(h.loc[entry, "adj_close"]) or pd.isna(h.loc[exit_session, "adj_close"])
                or h.loc[entry, "adj_close"] <= 0):
            missing.append(symbol)
            continue
        returns[symbol] = float(h.loc[exit_session, "adj_close"] / h.loc[entry, "adj_close"] * factor - 1)
    if missing:
        raise ValueError(f"Faltan precios ajustados en entrada/salida ({entry.date()} / "
                         f"{exit_session.date()}): {', '.join(missing)}")
    return {"end_date": exit_session.date().isoformat(),
            "portfolio_return": sum(returns[s] for s in symbols) / len(symbols),
            "benchmark_return": returns["SPY"]}


def run(start: str, end: str, months: int = 3, top_n: int = 10,
        cost_bps: float = 10, min_coverage: float = .7, min_universe_coverage: float = .7,
        max_symbols: int | None = None) -> dict:
    if not 1 <= months <= 12 or not 1 <= top_n <= 50 or cost_bps < 0:
        raise ValueError("Parámetros del backtest inválidos.")
    if not 0 < min_coverage <= 1 or not 0 < min_universe_coverage <= 1:
        raise ValueError("La cobertura debe estar entre 0 y 1.")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if start_ts >= end_ts or end_ts > pd.Timestamp(date.today()):
        raise ValueError("El intervalo debe terminar después del inicio y no superar hoy.")
    rows = []
    current = start_ts
    while current + pd.DateOffset(months=months) <= end_ts:
        as_of = current.date().isoformat()
        membership = universe.get_sp500_constituents_asof(as_of)
        if not membership["is_exact"]:
            raise ValueError(f"Sin composición histórica verificable para {as_of}: {membership['note']}")
        symbols = membership["symbols"][:max_symbols] if max_symbols else membership["symbols"]
        ranked = screener_asof.build_ranking_as_of(as_of, symbols=symbols)["table"]
        eligible = ranked[(ranked["composite_score"].notna())
                          & (ranked["score_coverage"] >= min_coverage)]
        if len(eligible) / len(symbols) < min_universe_coverage:
            raise ValueError(f"{as_of}: cobertura insuficiente del universo ({len(eligible)}/{len(symbols)}).")
        picks = eligible.head(top_n).index.tolist()
        if len(picks) < top_n:
            raise ValueError(f"{as_of}: solo {len(picks)}/{top_n} candidatas con cobertura suficiente.")
        outcome = _period_returns(picks, current, months, cost_bps)
        rows.append({"fecha": as_of, "hasta": outcome["end_date"],
                     "candidatas": ", ".join(picks), "cobertura universo": f"{len(eligible)}/{len(symbols)}",
                     "retorno": outcome["portfolio_return"], "spy": outcome["benchmark_return"]})
        current += pd.DateOffset(months=months)
    if not rows:
        raise ValueError("El intervalo no contiene ningún rebalanceo completo.")
    periods = pd.DataFrame(rows)
    periods["capital"] = (1 + periods["retorno"]).cumprod()
    periods["spy_capital"] = (1 + periods["spy"]).cumprod()
    return {"periods": periods, "return": float(periods["capital"].iloc[-1] - 1),
            "spy_return": float(periods["spy_capital"].iloc[-1] - 1),
            "drawdown": float((periods["capital"] / periods["capital"].cummax() - 1).min())}
