"""Synthetic parity and timing of cache writes and ledger provenance through the migrated facades."""

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

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
SYMBOLS, SESSIONS = 200, 250


def captured(source: str, names: set[str], namespace: dict) -> dict:
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in names or isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in names for target in node.targets):
            exec(ast.get_source_segment(source, node), namespace)
    return namespace


def dump(path: Path) -> dict:
    with closing(sqlite3.connect(path)) as db:
        return {table: sorted(db.execute(f"SELECT * FROM {table}").fetchall()) for table in ("prices", "splits")}


def main():
    from gabi import config, edgar, live_ledger, storage

    reference = json.loads((ROOT / "backend/tests/fixtures/legacy_facades_migration.json").read_text(encoding="utf-8"))
    frame = pd.DataFrame({"Open": 1., "High": 1., "Low": 1., "Close": [10. + i for i in range(SESSIONS)],
                          "Volume": 1e6, "Adj Close": [9. + i for i in range(SESSIONS)]},
                         index=pd.date_range("2024-01-01", periods=SESSIONS, freq="D"))
    results = {}
    with tempfile.TemporaryDirectory(prefix="gabi-facades-") as directory:
        paths = {label: Path(directory) / label / "gabi.db" for label in ("anterior", "nuevo")}
        counters = {"connections": 0, "schema": 0}
        real_connect = sqlite3.connect

        def connect(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            counters["connections"] += 1
            db.set_trace_callback(lambda s: counters.__setitem__(
                "schema", counters["schema"] + s.lstrip().upper().startswith(("CREATE", "ALTER"))))
            return db

        def connection(path):
            @contextmanager
            def get_connection():
                path.parent.mkdir(parents=True, exist_ok=True)
                with closing(sqlite3.connect(path, timeout=30)) as db:
                    db.execute("PRAGMA journal_mode=WAL")
                    yield db
            return get_connection

        old = captured(reference["storage"], {"SCHEMA", "_ensure_price_columns", "upsert_prices", "upsert_splits"},
                       {"get_connection": connection(paths["anterior"]), "pd": pd})

        def writes(upsert_prices, upsert_splits):
            def run():
                for i in range(SYMBOLS):
                    upsert_prices(f"S{i}", frame)
                    upsert_splits(f"S{i}", {"2024-03-01": 2.0})
            return run

        def provenance(path):
            ns = captured(reference["live_ledger"], {"provenance"}, {
                "storage": SimpleNamespace(get_connection=connection(path), SCHEMA=storage.SCHEMA,
                                           get_fundamentals_fetched_at=storage.get_fundamentals_fetched_at),
                "edgar": edgar, "_safe": live_ledger._safe})
            return ns["provenance"]

        symbols = [f"S{i}" for i in range(SYMBOLS)]
        flows = {
            "Escritura de precios y splits": (writes(old["upsert_prices"], old["upsert_splits"]),
                                              writes(storage.upsert_prices, storage.upsert_splits)),
            "Procedencia del ledger": (lambda: provenance(paths["anterior"])(symbols),
                                       lambda: live_ledger.provenance(symbols)),
        }
        sqlite3.connect = connect
        try:
            for name, variants in flows.items():
                outputs, row = [], {}
                for label, run in zip(("anterior", "nuevo"), variants):
                    config.DB_PATH = paths[label]
                    for key in counters:
                        counters[key] = 0
                    began = time.perf_counter()
                    output = run()
                    cold = time.perf_counter() - began
                    calls = dict(counters)
                    tracemalloc.start()
                    run()
                    peak = tracemalloc.get_traced_memory()[1] / 2**20
                    tracemalloc.stop()
                    warm = []
                    for _ in range(3):
                        began = time.perf_counter()
                        run()
                        warm.append(time.perf_counter() - began)
                    outputs.append(output if output is not None else dump(paths[label]))
                    row[label] = {"cold_s": round(cold, 4), "warm_median_s": round(statistics.median(warm), 4),
                                  "peak_python_mib": round(peak, 2), **calls}
                assert outputs[0] == outputs[1], name
                results[name] = row
        finally:
            sqlite3.connect = real_connect
    print(json.dumps({"symbols": SYMBOLS, "sessions": SESSIONS, "parity": True, "downloads": 0,
                      "measured_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                      "results": results}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
