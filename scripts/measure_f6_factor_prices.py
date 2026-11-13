"""Compare synthetic full-history and windowed Factor Lab price reads.

Usage: python scripts/measure_f6_factor_prices.py
Temporary SQLite only; this measures one price read, not a Factor Lab run.
"""

import gc
import sqlite3
import time
import tracemalloc
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from gabi import config, storage
from gabi.infrastructure.storage.factor_prices import SqliteFactorPrices


def measure(read):
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    result = read()
    elapsed = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1] / 1_048_576
    tracemalloc.stop()
    return result, elapsed, peak


def main() -> None:
    with TemporaryDirectory(prefix="gabi-factor-prices-") as directory:
        root = Path(directory)
        db_path = root / "gabi.db"
        symbols = [f"T{index:03d}" for index in range(50)]
        dates = pd.bdate_range("2016-01-01", "2024-12-31")
        with closing(sqlite3.connect(db_path)) as db:
            db.executescript(storage.SCHEMA)
            for symbol in symbols:
                db.executemany("INSERT INTO prices(symbol,date,adj_close) VALUES(?,?,?)",
                               ((symbol, day.date().isoformat(), 100.0)
                                for day in dates))
            db.commit()
        with patch.object(config, "DB_PATH", db_path), patch.object(config, "DATA_DIR", root):
            full, old_seconds, old_peak = measure(lambda: storage.get_prices_multi(symbols))
        first, last = "2023-01-01", "2023-12-31"
        window, new_seconds, new_peak = measure(
            lambda: SqliteFactorPrices(root)(symbols, first, last))
        assert all(window[symbol]["adj_close"].equals(
            full[symbol].loc[first:last, "adj_close"]) for symbol in symbols)
        print(f"symbols={len(symbols)} sessions_full={len(dates)} "
              f"sessions_window={len(next(iter(window.values())))}")
        print(f"full seconds={old_seconds:.4f} python_peak_mib={old_peak:.3f}")
        print(f"window seconds={new_seconds:.4f} python_peak_mib={new_peak:.3f}")
        del full, window
        gc.collect()


if __name__ == "__main__":
    main()
