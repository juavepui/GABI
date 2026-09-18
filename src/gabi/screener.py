"""Orquesta universo -> datos -> métricas -> técnicos -> riesgo -> scoring en una sola tabla."""
import pandas as pd

from . import config, storage, data_fetch, edgar, entity_master, macro, universe, metrics, technicals, risk, scoring


def get_universe(limit: int = None, force_refresh: bool = False) -> pd.DataFrame:
    uni = universe.get_sp500_constituents(force_refresh=force_refresh)
    if force_refresh:
        # Guarda una foto con fecha de sector/industria/nombre (entity_master)
        # cada vez que se confirma la composición actual del índice contra la
        # fuente en vivo -- así se acumula historial point-in-time real para
        # screener_asof.build_ranking_as_of, en vez de depender para siempre
        # del sector ACTUAL como aproximación de cualquier fecha pasada.
        entity_master.record_snapshot(uni)
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


def _get_risk_free_rate() -> float:
    """Treasury 10 años en vivo (vía FRED, si hay API key y datos cacheados);
    si no, la constante fija de config.RISK_FREE_RATE."""
    try:
        history = macro.get_series_history("DGS10")
        if not history.empty:
            return float(history["value"].iloc[-1]) / 100
    except Exception:
        pass
    return config.RISK_FREE_RATE


def build_screener_table(universe_df: pd.DataFrame, weights: dict = None, progress_cb=None) -> pd.DataFrame:
    """progress_cb(done, total), si se pasa, se llama cada ~25 empresas —
    todo el cálculo es sobre datos ya cacheados (sin red), pero con el
    universo completo (~500 empresas) puede tardar unos segundos y una
    barra de progreso evita que la pantalla parezca congelada."""
    symbols = universe_df["symbol"].tolist()
    fundamentals = storage.get_fundamentals(symbols)
    prices = storage.get_prices_multi(symbols)
    bench_df = storage.get_prices(config.BENCHMARK_SYMBOL)
    edgar_metrics = edgar.get_edgar_metrics(symbols)
    risk_free_rate = _get_risk_free_rate()

    rows = []
    total = len(universe_df)
    for i, (_, u) in enumerate(universe_df.iterrows()):
        sym = u["symbol"]
        record = fundamentals.get(sym)
        m = metrics.compute_fundamental_metrics(record) if record else {}
        p = prices.get(sym)
        t = technicals.compute_technicals(p, bench_df) if p is not None else {}
        r = risk.compute_risk_metrics(p, bench_df, risk_free_rate=risk_free_rate) if p is not None else {}
        edg = edgar_metrics.get(sym, {})

        row = {"symbol": sym, "name": u.get("name"), "sector": u.get("sector")}
        row.update(m)
        row.update(t)
        row.update(r)
        row["roic"] = edg.get("roic")
        row["revenue_cagr_3y"] = edg.get("revenue_cagr_3y")
        row["fcf_cagr_3y"] = edg.get("fcf_cagr_3y")
        row["latest_10k_url"] = edg.get("latest_10k_url")
        row["latest_10k_date"] = edg.get("latest_10k_date")
        row["latest_10q_url"] = edg.get("latest_10q_url")
        row["latest_10q_date"] = edg.get("latest_10q_date")
        rows.append(row)
        if progress_cb and (i % 25 == 0 or i == total - 1):
            progress_cb(i + 1, total)

    df = pd.DataFrame(rows).set_index("symbol")
    if df.empty:
        return df
    df = scoring.build_scores(df, weights=weights)
    df["confidence"] = scoring.compute_confidence(df, weights=weights)
    return df
