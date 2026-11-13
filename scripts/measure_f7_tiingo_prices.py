"""Measure complete initial and checkpoint-hit imports with exact SQL parity."""

import json
import runpy
import sqlite3
import statistics
import tempfile
import time
import tracemalloc
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def measure(call):
    tracemalloc.start()
    started = time.perf_counter()
    result = call()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed, peak / 1024**2


def main() -> None:
    fixture = runpy.run_path(str(ROOT / "backend/tests/test_tiingo_migration.py"))
    with tempfile.TemporaryDirectory(prefix="tiingo_measure_", dir=ROOT) as temporary:
        directory = Path(temporary).resolve()
        directory.relative_to(ROOT)
        cache_dir = directory / "cache"
        cache_dir.mkdir()
        dates = fixture["pd"].bdate_range("2008-01-01", "2016-06-30").strftime("%Y-%m-%d")
        symbols = [f"S{index:03}" for index in range(10)]
        for symbol in symbols:
            rows = [{**fixture["rows"]()[0], "date": day + "T00:00:00.000Z"} for day in dates]
            (cache_dir / f"{symbol}.json").write_bytes(json.dumps(rows).encode())
        readings = {mode: {name: [] for name in ["original", "migrated"]} for mode in ["initial", "checkpoint_hit"]}
        for repeat in range(4):
            outputs = {mode: {} for mode in readings}
            for name in readings["initial"]:
                db = directory / f"{name}_{repeat}.db"
                original = fixture["original"](cache_dir, db) if name == "original" else None
                cache = fixture["FileTiingoCache"](cache_dir)
                events, create = fixture["attempts"](db)

                def run():
                    if name == "original":
                        return original.import_cached()
                    with closing(sqlite3.connect(db)) as connection:
                        return fixture["import_cached"](fixture["window"]("2010-2015"), cache,
                            fixture["SqliteHistoricalPrices"](connection), events, attempt_factory=create)

                for mode in readings:
                    actual_connect = sqlite3.connect
                    counts = {"connections": 0, "selects": 0, "missing_table_selects": 0}

                    def trace(statement):
                        if statement.lstrip().upper().startswith("SELECT"):
                            counts["selects"] += 1

                    class MeasuredConnection(sqlite3.Connection):
                        def execute(self, statement, *args):
                            try:
                                return super().execute(statement, *args)
                            except sqlite3.OperationalError as exc:
                                if statement.lstrip().upper().startswith("SELECT") and "no such table:" in str(exc):
                                    # sqlite's trace callback does not report failed prepares.
                                    counts["selects"] += 1
                                    counts["missing_table_selects"] += 1
                                raise

                    def traced_connect(*args, **kwargs):
                        counts["connections"] += 1
                        connection = actual_connect(*args, **kwargs, factory=MeasuredConnection)
                        connection.set_trace_callback(trace)
                        return connection

                    sqlite3.connect = traced_connect
                    try:
                        result, seconds, peak = measure(run)
                    finally:
                        sqlite3.connect = actual_connect
                    readings[mode][name].append((seconds, peak, counts))
                    outputs[mode][name] = result, fixture["read_tables"](db)
            for mode in outputs:
                assert outputs[mode]["original"] == outputs[mode]["migrated"]
        results = {mode: {name: {"first_measured_seconds": data[0][0],
                                 "median_seconds": statistics.median(value[0] for value in data[1:]),
                                 "max_python_peak_mib": max(value[1] for value in data),
                                 "queries_per_run": data[-1][2]}
                          for name, data in values.items()} for mode, values in readings.items()}
        results.update(files=len(symbols), rows=len(dates) * len(symbols),
                       cache_bytes=sum(path.stat().st_size for path in cache_dir.glob("*.json")),
                       warm_repeats=3, downloads=0, parity="Full rows, metadata, events and checkpoints identical")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
