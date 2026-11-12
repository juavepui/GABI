"""The tested historical engine for today (#347): ``screener_asof`` in the operational mode of #237, with the
fiscal alignment of #38, exactly as the revalidation ``operativo-38`` (#35) and the prospective ensemble run it.

``record`` is the explicit write of the daily task: it stores the engine's eight company metrics for the active
universe in ``engine_fundamentals``, which GABI-MF-v5 scores with."""

from datetime import UTC, date, datetime

import pandas as pd

from gabi.domain.market import engine_fundamentals as rules
from gabi.infrastructure.settings import Settings


def ranking(settings: Settings, symbols: list[str], day: date, weights: dict, *, aligned: bool = True) -> pd.DataFrame:
    """The engine's full ranking of ``symbols`` on ``day`` (fundamentals by issuer, prices by ticker)."""
    from gabi import edgar, screener_asof
    from gabi.infrastructure.legacy.ensemble_live import check_engine_data
    from gabi.infrastructure.storage.sec_reads import SqliteSecReads

    check_engine_data(settings.data_dir)
    members = set(symbols)
    current = {symbol: f"cik:{int(cik):010d}" for symbol, cik in
               SqliteSecReads(settings.data_dir / "gabi.db").stored_ciks().items()
               if symbol in members and str(cik).strip().isdigit()}
    with edgar.fiscal_alignment(aligned):
        return screener_asof.build_ranking_as_of(day.isoformat(), weights=weights, symbols=symbols,
                                                 operational_entities=current)["table"]


def record(settings: Settings, day: date) -> dict:
    """Compute and store today's engine metrics for the live universe; returns a short report."""
    from gabi.infrastructure.legacy.market import calculators, model_policy
    from gabi.infrastructure.model_versions import active_model
    from gabi.infrastructure.storage import ranking_revision
    from gabi.infrastructure.storage.engine_fundamentals import SqliteEngineFundamentals
    from gabi.infrastructure.storage.market import ReadOnlyMarket

    model = active_model()
    market = ReadOnlyMarket(settings, calculators(model.technical), model_policy(model), model.benchmark_symbol,
                            model.risk_free_rate, metrics_version=model.metrics_version)
    try:
        symbols = [str(symbol) for symbol in market.universe(market.small_file("sp500_constituents.csv"))["symbol"]]
    finally:
        market.close()
    if not symbols:
        return {"guardadas": 0, "motivo": "sin universo"}
    table = ranking(settings, symbols, day, dict(model.weights))
    rows = rules.rows(table, day)
    database = settings.data_dir / "gabi.db"
    saved = SqliteEngineFundamentals(database).replace(rows, datetime.now(UTC))
    # The table may be new: count its changes from now on (idempotent, #342).
    ranking_revision.install(database)
    complete = sum(all(row[metric] is not None for metric in rules.METRICS) for row in rows)
    return {"dia": day.isoformat(), "regla": rules.RULE_VERSION, "guardadas": saved, "completas": complete}
