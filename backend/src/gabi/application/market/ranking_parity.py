"""The app's ranking against the historical engine's on the same day (#291); reads the local cache only.

The app scores Value and part of Quality with Yahoo's last twelve months or last
quarter; the historical engine (``screener_asof``, operational mode of #237)
computes them from the annual SEC 10-K (fiscal alignment of #38) and that day's price. GABI-MF-v5
(#347) scores with that engine's company metrics, so with it both rankings should agree. Both rankings use
the same universe, weights and scoring; the report says how much they agree and
which metric explains the largest moves. It does not decide anything: declaring
a model version with SEC metrics is a separate change (ADR 0008).
"""

from collections.abc import Callable
from datetime import date

import pandas as pd

from gabi.domain.market import metrics_comparison as compare
from gabi.domain.market.metric_sources import metric_sources

# v2 (#347): the engine runs with the fiscal alignment of #38, as tested; live sources follow the version.
VERSION = "ranking-parity-v2"
TOP_N = 20
# The historical engine: every fundamental from the latest 10-K known that day; prices from the cache.
HISTORICAL_SOURCES: dict[str, tuple[str, str]] = {
    "pe": ("sec_10k", "fiscal_year"), "pb": ("sec_10k", "fiscal_year"), "ev_ebitda": ("sec_10k", "fiscal_year"),
    "roic": ("sec_10k", "fiscal_year"), "operating_margin": ("sec_10k", "fiscal_year"),
    "revenue_cagr_3y": ("sec_10k", "fiscal_years_3"), "fcf_cagr_3y": ("sec_10k", "fiscal_years_3"),
    "debt_to_equity": ("sec_10k", "fiscal_year"),
    "momentum_12m": ("prices", "12m"), "rel_strength_6m": ("prices", "6m"), "price_vs_sma200": ("prices", "200d"),
    "volatility": ("prices", "cached_history"), "max_drawdown": ("prices", "cached_history"),
}
LIVE_EXTRA: dict[str, tuple[str, str]] = {"rel_strength_6m": ("prices", "6m"), "price_vs_sma200": ("prices", "200d")}


def compare_rankings(*, universe: Callable[[], list[str]], live: Callable[[], pd.DataFrame],
                     historical: Callable[[list[str], date], pd.DataFrame], weights: dict[str, float],
                     score_metrics: dict[str, list[str]], model_id: str, metrics_version: str, today: date,
                     progress: Callable[[float, str], None] = lambda share, phase: None) -> dict:
    """Both rankings over the app's universe on ``today``, with the active model's weights."""
    symbols = universe()
    progress(0.05, "Ranking de la app")
    app = live()
    progress(0.2, "Ranking con el cálculo histórico")
    past = historical(symbols, today)
    progress(0.95, "Comparando")
    sources = {"live": {**metric_sources(metrics_version), **LIVE_EXTRA}, "historical": HISTORICAL_SOURCES}
    report = compare.live_vs_historical(app, past, weights=weights, score_metrics=score_metrics,
                                        sources=sources, top_n=TOP_N)
    return {"version": VERSION, "as_of": today.isoformat(), "model_id": model_id,
            "metrics_version": metrics_version, "weights": dict(weights), **report}
