"""Orquesta universo -> datos -> métricas -> técnicos -> riesgo -> scoring en una sola tabla."""
from datetime import UTC, date, datetime

import pandas as pd

from gabi.application.market import cached_data
from gabi.application.market.ranking import Calculators, MarketBatch, MemoryInputs, build_ranking
from gabi.application.market.sec_reads import cached_metrics
from gabi.domain.market import events as events_calendar
from gabi.domain.market.fundamentals import compute_fundamental_metrics
from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
from gabi.infrastructure.storage.fred import SqliteFred
from gabi.infrastructure.storage.sec_reads import SqliteSecReads

from . import (
    config,
    entity_master,
    risk,
    scoring,
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


def _get_risk_free_rate() -> float:
    """Treasury 10 años en vivo (vía FRED, si hay API key y datos cacheados);
    si no, la constante fija de config.RISK_FREE_RATE."""
    try:
        history = SqliteFred(config.DB_PATH, lambda: datetime.now(UTC)).history("DGS10")
        if not history.empty:
            return float(history["value"].iloc[-1]) / 100
    except Exception:
        pass
    return config.RISK_FREE_RATE


def build_screener_table(universe_df: pd.DataFrame, weights: dict = None, progress_cb=None) -> pd.DataFrame:
    """Compatibility facade over the shared ranking use case and read-only, bounded cache readers.

    The HTTP adapter batches the same inputs with its own budgets and ranking cache.
    """
    symbols = universe_df["symbol"].tolist()
    # The compatibility path is captured per operation, never mutated.
    cache = SqliteCacheReads(config.DB_PATH)
    inputs = MemoryInputs(
        MarketBatch(universe_df, cached_data.fundamentals(cache, symbols), cached_data.prices_multi(cache, symbols),
                    cached_metrics(SqliteSecReads(config.DB_PATH), symbols)),
        cached_data.prices(cache, config.BENCHMARK_SYMBOL), config.BENCHMARK_SYMBOL, _get_risk_free_rate(),
    )
    calculators = Calculators(compute_fundamental_metrics, technicals.compute_technicals,
                              risk.compute_risk_metrics, events_calendar.parse_corporate_events,
                              scoring.build_scores, scoring.compute_confidence)
    return build_ranking(inputs, calculators, weights, today=date.today(), total=len(universe_df), progress_cb=progress_cb)
