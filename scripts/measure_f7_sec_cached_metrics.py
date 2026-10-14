"""Synthetic parity and cold/warm measurement of cached EDGAR metric reads."""

import ast
import json
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
NAMES = {"SCHEMA", "FACTS_SCHEMA", "get_edgar_metrics", "get_symbols_with_facts", "get_edgar_fetched_at"}
SYMBOLS, FACTS_PER_SYMBOL = 500, 40


def main():
    from gabi.application.market.sec_reads import cached_metrics, fetched_at, symbols_with_facts
    from gabi.infrastructure.storage.sec_reads import SqliteSecReads

    reference = json.loads((ROOT / "backend/tests/fixtures/sec_cached_metrics_migration.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="gabi-sec-cached-") as directory:
        path = Path(directory) / "gabi.db"
        counters = {"connections": 0, "selects": 0, "schema": 0}

        def trace(statement):
            head = statement.lstrip().upper()
            counters["selects"] += head.startswith("SELECT")
            counters["schema"] += head.startswith("CREATE")

        real_connect = sqlite3.connect

        def connect(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            counters["connections"] += 1
            db.set_trace_callback(trace)
            return db

        @contextmanager
        def connection():
            with closing(sqlite3.connect(path)) as db:
                yield db

        namespace = {"storage": SimpleNamespace(get_connection=connection), "datetime": datetime}
        for node in ast.parse(reference["edgar"]).body:
            if isinstance(node, ast.FunctionDef) and node.name in NAMES or isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id in NAMES for target in node.targets):
                exec(ast.get_source_segment(reference["edgar"], node), namespace)
        with connection() as db:
            db.executescript(namespace["SCHEMA"] + namespace["FACTS_SCHEMA"])
            for i in range(SYMBOLS):
                db.execute("INSERT INTO edgar_metrics VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (f"S{i}", str(i), datetime(2026, 1, 1, tzinfo=UTC).isoformat(), 0.1, 0.2, 0.3,
                            "2025-02-01", "https://sec.example/k", "2025-11-01", "https://sec.example/q"))
                db.executemany("INSERT INTO edgar_facts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               [(f"S{i}", "Revenues", "USD", "2024-01-01", "2024-12-31", 1.0, "10-K", "FY", 2024,
                                 "2025-02-01", f"{i}-{n}") for n in range(FACTS_PER_SYMBOL)])
            db.commit()
        symbols = [f"S{i}" for i in range(SYMBOLS)]
        reader = SqliteSecReads(path)
        flows = {
            "Métricas cacheadas": (lambda: namespace["get_edgar_metrics"](symbols), lambda: cached_metrics(reader, symbols)),
            "Fecha de descarga": (lambda: namespace["get_edgar_fetched_at"](symbols), lambda: fetched_at(reader, symbols)),
            "Símbolos con hechos": (lambda: namespace["get_symbols_with_facts"](symbols), lambda: symbols_with_facts(reader, symbols)),
        }
        sqlite3.connect = connect
        try:
            results = {}
            for name, variants in flows.items():
                outputs, row = [], {}
                for label, run in zip(("anterior", "nuevo"), variants):
                    for key in counters:
                        counters[key] = 0
                    tracemalloc.start()
                    start = time.perf_counter()
                    output = run()
                    cold = time.perf_counter() - start
                    peak = tracemalloc.get_traced_memory()[1] / 2**20
                    tracemalloc.stop()
                    calls = dict(counters)
                    warm = []
                    for _ in range(3):
                        start = time.perf_counter()
                        run()
                        warm.append(time.perf_counter() - start)
                    outputs.append(output)
                    row[label] = {"cold_s": round(cold, 4), "warm_median_s": round(statistics.median(warm), 4),
                                  "peak_python_mib": round(peak, 4), **calls}
                assert outputs[0] == outputs[1], name
                results[name] = row
        finally:
            sqlite3.connect = real_connect
    print(json.dumps({"symbols": SYMBOLS, "facts": SYMBOLS * FACTS_PER_SYMBOL, "parity": True, "downloads": 0,
                      "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
