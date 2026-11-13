"""Measure full synthetic SEC map/resolution operations and exact persisted parity."""

import json
import os
import runpy
import sqlite3
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def main():
    fixture = runpy.run_path(str(ROOT / "backend/tests/test_sec_cik_migration.py"))
    payload = {str(i): {"ticker": f"S{i:05}", "cik_str": i + 1, "title": f"Compañía {i}, synthetic"}
               for i in range(5000)}
    symbols = [f"S{i:05}" for i in range(50)]
    samples = {mode: {name: [] for name in ("original", "migrated")}
               for mode in ("initial_and_resolve", "map_cache_hit", "forced_and_resolve")}
    cache_bytes = 0
    with tempfile.TemporaryDirectory(prefix="sec_cik_measure_", dir=ROOT) as temporary:
        directory = Path(temporary).resolve()
        directory.relative_to(ROOT)
        for repeat in range(4):
            outputs = {mode: {} for mode in samples}
            for name in samples["initial_and_resolve"]:
                target = directory / f"{name}_{repeat}"
                with pytest.MonkeyPatch.context() as monkeypatch:
                    old = fixture["original"](target, [payload, payload], monkeypatch) if name == "original" else None
                    service = fixture["modern"](target, [payload, payload]) if name == "migrated" else None
                    for mode in samples:
                        def run():
                            force = mode == "forced_and_resolve"
                            frame = old.get_cik_map(force_refresh=force) if old else service.mapping(force_refresh=force)
                            resolutions = []
                            if mode != "map_cache_hit":
                                for symbol in symbols:
                                    resolutions.append(old.get_cik_for_symbol(symbol, frame) if old else service.resolve(symbol, frame))
                                    resolutions.append(old._get_cached_cik_resolution(symbol) if old else service.resolutions.cached(symbol))
                            return frame, resolutions
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
                        path = target / "sec_cik_map.csv"
                        os.utime(path, (fixture["NOW"].timestamp(), fixture["NOW"].timestamp()))
                        raw = path.read_bytes()
                        cache_bytes = len(raw)
                        outputs[mode][name] = result, raw, fixture["read_tables"](target / "gabi.db")
            for values in outputs.values():
                old_result, old_raw, old_tables = values["original"]
                new_result, new_raw, new_tables = values["migrated"]
                fixture["pd"].testing.assert_frame_equal(old_result[0], new_result[0])
                assert old_result[1] == new_result[1] and old_raw == new_raw and old_tables == new_tables
    results = {mode: {name: {"first_seconds": values[0][0],
                            "warm_median_seconds": statistics.median(v[0] for v in values[1:]),
                            "max_python_peak_mib": max(v[1] for v in values), "queries": values[-1][2]}
                      for name, values in names.items()} for mode, names in samples.items()}
    results.update(map_rows=len(payload), resolutions=len(symbols), cache_bytes=cache_bytes,
                   downloads=0, warm_repeats=3, parity="CSV bytes, frames, resolutions, events and checkpoints identical")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
