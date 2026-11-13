"""Inputs of the NSI-v1 exploratory evaluation (#252): the same market, splits and sectors as the V3 comparison."""

from pathlib import Path

import pandas as pd


def inputs(data_dir: Path) -> dict:
    from gabi import config, entity_master, multifactor_backtest
    from gabi.infrastructure.storage.simulations import SqliteSimulations
    from gabi.infrastructure.storage.ticker_prices import SqliteTickerPrices

    fx = SqliteSimulations(data_dir).prices(["USDEUR=X"], "2010-01-01").get("USDEUR=X")
    if fx is None or fx.empty:
        raise SystemExit("Falta USDEUR=X en caché: actualiza el benchmark antes de evaluar.")
    return {
        "market": multifactor_backtest.market(issuer_history=True),
        "splits": SqliteTickerPrices(config.DB_PATH).splits_many,
        "sectors": lambda symbols, as_of: {symbol: row["sector"] for symbol, row in
                                           entity_master.get_sector_asof(symbols, as_of).items()},
        "euros_per_dollar": fx["close"],
        "factors": pd.read_csv(data_dir / "ff_factors.csv"),
    }
