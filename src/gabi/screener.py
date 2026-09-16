"""Orquesta universo -> datos -> métricas -> técnicos -> scoring en una sola tabla."""
import pandas as pd

from . import config, storage, data_fetch, edgar, universe, metrics, technicals, scoring


def get_universe(limit: int = None, force_refresh: bool = False) -> pd.DataFrame:
    uni = universe.get_sp500_constituents(force_refresh=force_refresh)
    if limit:
        uni = uni.head(limit)
    return uni


def refresh_data(symbols: list, force: bool = False, progress_cb=None, edgar_progress_cb=None) -> dict:
    """Actualiza yfinance (precios + fundamentales) y SEC EDGAR (ROIC, CAGR de
    3 años, enlaces a 10-K/10-Q). Los fallos de ambas fuentes se combinan en
    un único dict[symbol] = {"precio":.., "fundamentales":.., "edgar":..}."""
    result = data_fetch.ensure_universe_data(symbols, force=force, progress_cb=progress_cb)
    edgar_result = edgar.ensure_edgar_data(symbols, force=force, progress_cb=edgar_progress_cb or progress_cb)

    for sym, reason in edgar_result["failed"].items():
        result["failed"].setdefault(sym, {})["edgar"] = reason
    result["edgar_refreshed"] = edgar_result["edgar_refreshed"]
    return result


def build_screener_table(universe_df: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    symbols = universe_df["symbol"].tolist()
    fundamentals = storage.get_fundamentals(symbols)
    prices = storage.get_prices_multi(symbols)
    bench_df = storage.get_prices(config.BENCHMARK_SYMBOL)
    edgar_metrics = edgar.get_edgar_metrics(symbols)

    rows = []
    for _, u in universe_df.iterrows():
        sym = u["symbol"]
        record = fundamentals.get(sym)
        m = metrics.compute_fundamental_metrics(record) if record else {}
        p = prices.get(sym)
        t = technicals.compute_technicals(p, bench_df) if p is not None else {}
        edg = edgar_metrics.get(sym, {})

        row = {"symbol": sym, "name": u.get("name"), "sector": u.get("sector")}
        row.update(m)
        row.update(t)
        row["roic"] = edg.get("roic")
        row["revenue_cagr_3y"] = edg.get("revenue_cagr_3y")
        row["fcf_cagr_3y"] = edg.get("fcf_cagr_3y")
        row["latest_10k_url"] = edg.get("latest_10k_url")
        row["latest_10k_date"] = edg.get("latest_10k_date")
        row["latest_10q_url"] = edg.get("latest_10q_url")
        row["latest_10q_date"] = edg.get("latest_10q_date")
        rows.append(row)

    df = pd.DataFrame(rows).set_index("symbol")
    if df.empty:
        return df
    return scoring.build_scores(df, weights=weights)
