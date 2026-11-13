"""Synthetic parity and cold/warm measurement of the cached price/fundamental reads."""

import ast
import json
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
NAMES = {"SCHEMA", "_ensure_price_columns", "get_prices", "get_prices_multi", "get_price_coverage",
         "get_fundamentals", "get_split_factor_since"}
SYMBOLS, SESSIONS = 500, 1250


def same(left, right):
    if isinstance(left, dict) and left and isinstance(next(iter(left.values())), pd.DataFrame):
        return list(left) == list(right) and all(left[key].equals(right[key]) for key in left)
    if isinstance(left, pd.DataFrame):
        return left.equals(right)
    return left == right


def main():
    from gabi.application.market import cached_data
    from gabi.infrastructure.storage.cache_reads import SqliteCacheReads

    reference = json.loads((ROOT / "backend/tests/fixtures/storage_cache_reads_migration.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="gabi-storage-reads-") as directory:
        path = Path(directory) / "gabi.db"
        counters = {"selects": 0, "schema": 0}

        def trace(statement):
            head = statement.lstrip().upper()
            counters["selects"] += head.startswith("SELECT")
            counters["schema"] += head.startswith(("CREATE", "ALTER"))

        real_connect = sqlite3.connect

        def connect(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            db.set_trace_callback(trace)
            return db

        @contextmanager
        def get_connection():
            with closing(sqlite3.connect(path, timeout=30)) as db:
                yield db

        namespace = {"get_connection": get_connection, "pd": pd, "json": json, "datetime": datetime}
        for node in ast.parse(reference["storage"]).body:
            if isinstance(node, ast.FunctionDef) and node.name in NAMES or isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id in NAMES for target in node.targets):
                exec(ast.get_source_segment(reference["storage"], node), namespace)
        start_day = datetime(2020, 1, 1)
        with get_connection() as db:
            db.executescript(namespace["SCHEMA"])
            for i in range(SYMBOLS):
                db.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)",
                               [(f"S{i}", (start_day + timedelta(days=d)).strftime("%Y-%m-%d"), 10.0, 11.0, 9.0,
                                 10.0 + d / 100, 1000.0, 10.0 + d / 100) for d in range(SESSIONS)])
                db.execute("INSERT INTO fundamentals VALUES (?,?,?,?,?)",
                           (f"S{i}", datetime.now(UTC).isoformat(), json.dumps({"sector": "Tech", "beta": 1.1}),
                            json.dumps({"2024-03-31": {"Total Revenue": 1e9}}), "{}"))
                db.execute("INSERT INTO splits VALUES (?,?,?)", (f"S{i}", "2021-06-01", 2.0))
            db.commit()
        symbols = [f"S{i}" for i in range(SYMBOLS)]
        reader = SqliteCacheReads(path)
        flows = {
            "Precios de un símbolo": (lambda: namespace["get_prices"]("S7"), lambda: cached_data.prices(reader, "S7")),
            "Precios del universo": (lambda: namespace["get_prices_multi"](symbols),
                                     lambda: cached_data.prices_multi(reader, symbols)),
            "Cobertura de precios": (lambda: namespace["get_price_coverage"](symbols),
                                     lambda: cached_data.price_coverage(reader, symbols)),
            "Fundamentales": (lambda: namespace["get_fundamentals"](symbols),
                              lambda: cached_data.fundamentals(reader, symbols)),
            "Factor de split": (lambda: namespace["get_split_factor_since"]("S7", "2020-06-01"),
                                lambda: cached_data.split_factor_since(reader, "S7", "2020-06-01")),
        }
        sqlite3.connect = connect
        try:
            results = {}
            for name, variants in flows.items():
                outputs, row = [], {}
                for label, run in zip(("anterior", "nuevo"), variants):
                    for key in counters:
                        counters[key] = 0
                    began = time.perf_counter()
                    output = run()
                    cold = time.perf_counter() - began
                    calls = dict(counters)
                    # Allocation tracing slows allocation-heavy paths, so it gets its own run.
                    tracemalloc.start()
                    run()
                    peak = tracemalloc.get_traced_memory()[1] / 2**20
                    tracemalloc.stop()
                    warm = []
                    for _ in range(3):
                        began = time.perf_counter()
                        run()
                        warm.append(time.perf_counter() - began)
                    outputs.append(output)
                    row[label] = {"cold_s": round(cold, 4), "warm_median_s": round(statistics.median(warm), 4),
                                  "peak_python_mib": round(peak, 2), **calls}
                assert same(outputs[0], outputs[1]), name
                results[name] = row
        finally:
            sqlite3.connect = real_connect
    print(json.dumps({"symbols": SYMBOLS, "price_rows": SYMBOLS * SESSIONS, "parity": True, "downloads": 0,
                      "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
