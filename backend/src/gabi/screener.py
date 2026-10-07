"""Orquesta universo -> datos -> métricas -> técnicos -> riesgo -> scoring en una sola tabla."""
from datetime import date

import pandas as pd

from gabi.application.market.ranking import Calculators, MarketBatch, MemoryInputs, build_ranking
from gabi.domain.market import events as events_calendar

from . import (
    config,
    data_fetch,
    edgar,
    entity_master,
    macro,
    metrics,
    risk,
    scoring,
    storage,
    technicals,
    universe,
)


def get_universe(limit: int = None, force_refresh: bool = False) -> pd.DataFrame:
    uni = universe.get_sp500_constituents(force_refresh=force_refresh)
    if force_refresh and not uni.attrs.get("cache_after_error"):
        # Guarda una foto con fecha de sector/industria/nombre (entity_master)
        # cada vez que se confirma la composición actual del índice contra la
        # fuente en vivo -- así se acumula historial point-in-time real para
        # screener_asof.build_ranking_as_of, en vez de depender para siempre
        # del sector ACTUAL como aproximación de cualquier fecha pasada.
        entity_master.record_snapshot(uni)
    if limit:
        uni = uni.head(limit)
    return uni


def refresh_data(symbols: list, force: bool = False, progress_cb=None, edgar_progress_cb=None,
                 *, full_refresh: bool = False) -> dict:
    """Actualiza yfinance (precios + fundamentales) y SEC EDGAR (ROIC, CAGR de
    3 años, enlaces a 10-K/10-Q). Los fallos de ambas fuentes se combinan en
    un único dict[symbol] = {"precio":.., "fundamentales":.., "edgar":..}."""
    result = data_fetch.ensure_universe_data(symbols, force=force, progress_cb=progress_cb, full_refresh=full_refresh)
    edgar_result = edgar.ensure_edgar_data(symbols, force=force, progress_cb=edgar_progress_cb or progress_cb,
                                         full_refresh=full_refresh)

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
    """Compatibility facade: Streamlit and HTTP use the same ranking use case.

    This existing adapter retains its storage behaviour. The HTTP adapter uses
    explicitly read-only, bounded SQL instead of these schema-initializing getters.
    """
    symbols = universe_df["symbol"].tolist()
    inputs = MemoryInputs(
        MarketBatch(universe_df, storage.get_fundamentals(symbols), storage.get_prices_multi(symbols),
                    edgar.get_edgar_metrics(symbols)),
        storage.get_prices(config.BENCHMARK_SYMBOL), config.BENCHMARK_SYMBOL, _get_risk_free_rate(),
    )
    calculators = Calculators(metrics.compute_fundamental_metrics, technicals.compute_technicals,
                              risk.compute_risk_metrics, events_calendar.parse_corporate_events,
                              scoring.build_scores, scoring.compute_confidence)
    return build_ranking(inputs, calculators, weights, today=date.today(), total=len(universe_df), progress_cb=progress_cb)
