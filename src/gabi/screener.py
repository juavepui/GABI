"""Orquesta universo -> datos -> métricas -> técnicos -> scoring en una sola tabla."""
import pandas as pd

from . import config, storage, data_fetch, universe, metrics, technicals, scoring


def get_universe(limit: int = None, force_refresh: bool = False) -> pd.DataFrame:
    uni = universe.get_sp500_constituents(force_refresh=force_refresh)
    if limit:
        uni = uni.head(limit)
    return uni


def refresh_data(symbols: list, force: bool = False, progress_cb=None) -> dict:
    return data_fetch.ensure_universe_data(symbols, force=force, progress_cb=progress_cb)


def build_screener_table(universe_df: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    symbols = universe_df["symbol"].tolist()
    fundamentals = storage.get_fundamentals(symbols)
    prices = storage.get_prices_multi(symbols)
    bench_df = storage.get_prices(config.BENCHMARK_SYMBOL)

    rows = []
    for _, u in universe_df.iterrows():
        sym = u["symbol"]
        record = fundamentals.get(sym)
        m = metrics.compute_fundamental_metrics(record) if record else {}
        p = prices.get(sym)
        t = technicals.compute_technicals(p, bench_df) if p is not None else {}

        row = {"symbol": sym, "name": u.get("name"), "sector": u.get("sector")}
        row.update(m)
        row["name"] = row.get("name") or u.get("name")
        row["sector"] = row.get("sector") or u.get("sector")
        row.update(t)
        rows.append(row)

    df = pd.DataFrame(rows).set_index("symbol")
    if df.empty:
        return df
    return scoring.build_scores(df, weights=weights)
