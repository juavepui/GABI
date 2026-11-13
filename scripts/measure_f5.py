"""Compare legacy and F5 decision price reads on synthetic local data only."""

import argparse
import gc
import json
import platform
import sqlite3
import sys
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/tests"))
from market_fixture import seed_fixture  # noqa: E402

from gabi import config, storage  # noqa: E402
from gabi.infrastructure.storage.decisions import SqliteDecisions  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=int, default=100)
    parser.add_argument("--sessions", type=int, default=500)
    args = parser.parse_args()
    if not 1 <= args.companies <= 996 or not 253 <= args.sessions <= 2000:
        parser.error("companies: 1..996; sessions: 253..2000")
    with TemporaryDirectory(prefix="gabi-f5-measure-") as temporary:
        root = Path(temporary).resolve()
        assert root.is_relative_to(Path(gettempdir()).resolve())
        assert root.name.startswith("gabi-f5-measure-")
        universe = seed_fixture(root, args.companies, args.sessions)
        symbols = universe["symbol"].tolist()
        old_data = config.DATA_DIR
        old_paths = {name: value for name, value in vars(config).items()
                     if isinstance(value, Path) and value.is_relative_to(old_data)}
        for name, value in old_paths.items():
            setattr(config, name, root / value.relative_to(old_data))
        connect = sqlite3.connect
        statements: list[str] = []

        def observed_connect(*positional, **kwargs):
            db = connect(*positional, **kwargs)
            db.set_trace_callback(statements.append)
            return db

        sqlite3.connect = observed_connect

        def measure(operation):
            gc.collect()
            statements.clear()
            tracemalloc.start()
            start = perf_counter()
            value = operation()
            elapsed = perf_counter() - start
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            return value, {"seconds": round(elapsed, 4), "peak_python_mib": round(peak / 1024**2, 3),
                           "select_queries": sum(sql.lstrip().upper().startswith("SELECT") for sql in statements)}

        try:
            legacy, baseline = measure(lambda: storage.get_prices_multi(symbols))
            current, modern = measure(lambda: SqliteDecisions(root).histories(symbols))
            for symbol in symbols:
                prior = legacy.get(symbol, pd.DataFrame())
                after = current.get(symbol, pd.DataFrame())
                if prior.empty:
                    assert after.empty
                else:
                    pd.testing.assert_series_equal(prior["adj_close"], after["adj_close"], check_names=True)
            print(json.dumps({"python": platform.python_version(), "platform": platform.system(),
                              "companies": len(symbols), "sessions": args.sessions,
                              "price_rows": sum(len(frame) for frame in current.values()),
                              "adjusted_closes_equal": True,
                              "memory_scope": "tracemalloc Python allocations, excluding native RSS",
                              "legacy": baseline, "f5_batched": modern}, indent=2))
        finally:
            sqlite3.connect = connect
            for name, value in old_paths.items():
                setattr(config, name, value)


if __name__ == "__main__":
    main()
