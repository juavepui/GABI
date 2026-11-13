"""Complete synthetic FRED refresh and cache-hit measurements with SQL parity."""

import json
import runpy
import sqlite3
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def main():
    fixture = runpy.run_path(str(ROOT / "backend/tests/test_fred_migration.py"))
    series = {f"S{i:02}": {"units_param": "lin"} for i in range(9)}
    dates = pd.date_range("1990-01-01", "2024-01-01").strftime("%Y-%m-%d")
    payload = [(day, None if i % 97 == 0 else float(i % 100)) for i, day in enumerate(dates)]
    samples = {mode: {name: [] for name in ["original", "migrated"]} for mode in ["initial", "cache_hit"]}
    with tempfile.TemporaryDirectory(prefix="fred_measure_", dir=ROOT) as temporary:
        directory = Path(temporary).resolve()
        directory.relative_to(ROOT)
        for repeat in range(4):
            outputs = {mode: {} for mode in samples}
            for name in samples["initial"]:
                path = directory / f"{name}_{repeat}.db"
                with pytest.MonkeyPatch.context() as monkeypatch:
                    old, sync = fixture["original"](path, monkeypatch)
                    old["SERIES"] = series
                    old["fetch_series"] = lambda *args, **kwargs: payload
                    monkeypatch.setattr(sync, "retry", lambda call, attempt: fixture["counted"](call, attempt))
                    _, _, _, modern = fixture["modern"](path, series=series)
                    def run():
                        return old["ensure_macro_data"]() if name == "original" else modern(lambda *a, **kw: payload)
                    for mode in samples:
                        actual = sqlite3.connect
                        counts = {"connections": 0, "selects": 0, "missing_table_selects": 0}
                        def trace(statement):
                            if statement.lstrip().upper().startswith("SELECT"):
                                counts["selects"] += 1
                        class Measured(sqlite3.Connection):
                            def execute(self, statement, *args):
                                try:
                                    return super().execute(statement, *args)
                                except sqlite3.OperationalError as exc:
                                    if statement.lstrip().upper().startswith("SELECT") and "no such table:" in str(exc):
                                        counts["selects"] += 1
                                        counts["missing_table_selects"] += 1
                                    raise
                        def connect(*args, **kwargs):
                            counts["connections"] += 1
                            db = actual(*args, **kwargs, factory=Measured)
                            db.set_trace_callback(trace)
                            return db
                        sqlite3.connect = connect
                        tracemalloc.start()
                        started = time.perf_counter()
                        try:
                            result = run()
                            seconds = time.perf_counter() - started
                            _, peak = tracemalloc.get_traced_memory()
                        finally:
                            tracemalloc.stop()
                            sqlite3.connect = actual
                        samples[mode][name].append((seconds, peak / 1024**2, counts))
                        outputs[mode][name] = result, fixture["tables"](path)
            for values in outputs.values():
                assert values["original"] == values["migrated"]
    results = {mode: {name: {"first_seconds": values[0][0],
                            "warm_median_seconds": statistics.median(v[0] for v in values[1:]),
                            "max_python_peak_mib": max(v[1] for v in values),
                            "queries": values[-1][2]} for name, values in names.items()}
               for mode, names in samples.items()}
    results.update(series=len(series), rows=len(payload) * len(series),
                   payload_bytes=len(json.dumps(payload).encode()) * len(series),
                   downloads=0, warm_repeats=3, parity="All rows, metadata, checkpoints and events identical")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
