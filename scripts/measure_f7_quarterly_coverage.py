"""Measure the complete original/new quarterly command on synthetic inputs."""

import contextlib
import io
import json
import runpy
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    sys.path.insert(0, str(ROOT / "backend/tests"))
    fixture = runpy.run_path(str(ROOT / "backend/tests/test_quarterly_coverage_migration.py"))
    readings: dict[str, list[tuple[float, float]]] = {"original": [], "migrated": []}
    queries = {"original": 0, "migrated": 0}
    with tempfile.TemporaryDirectory(prefix="quarterly_measure_", dir=ROOT) as temporary:
        directory = Path(temporary).resolve()
        directory.relative_to(ROOT)
        db, before, live = fixture["make_quarterly_inputs"](directory)
        old_output = directory / "reference/coverage"
        old_output.parent.mkdir()
        new_output = directory / "migrated"

        def trace(name, sql):
            queries[name] += sql.lstrip().upper().startswith("SELECT")

        def original():
            return fixture["original_command"](db, before, live, old_output, trace=lambda sql: trace("original", sql))

        def migrated():
            with contextlib.closing(fixture["connect_readonly"](db)) as connection, \
                    contextlib.closing(fixture["connect_readonly"](before)) as old_connection:
                connection.set_trace_callback(lambda sql: trace("migrated", sql))
                old_connection.set_trace_callback(lambda sql: trace("migrated", sql))
                return fixture["publish"](fixture["reader"](connection, old_connection, live), fixture["sessions"](),
                                           fixture["FileQuarterlyCoverage"](new_output))

        with contextlib.redirect_stdout(io.StringIO()):
            reference = original()
            assert migrated() == reference
            for _ in range(3):
                for name, run in (("original", original), ("migrated", migrated)):
                    queries[name] = 0
                    tracemalloc.start()
                    start = time.perf_counter()
                    assert run() == reference
                    elapsed = time.perf_counter() - start
                    _, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    readings[name].append((elapsed, peak / 1024**2))
                for path in old_output.iterdir():
                    assert path.read_bytes() == (new_output / path.name).read_bytes()
        result = {name: {"median_seconds": statistics.median(row[0] for row in rows),
                         "max_python_peak_mib": max(row[1] for row in rows), "select_queries": queries[name]}
                  for name, rows in readings.items()}
        with contextlib.closing(fixture["connect_readonly"](db)) as connection:
            volumes = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                       for table in ("prices", "historical_prices", "entity_observations")}
        result.update({"quarters": reference["quarters"], "company_quarters": reference["company_quarters"],
                       "repeats": 3, "input_rows": volumes,
                       "parity": "All four CSV and summary JSON bytes match on every repetition"})
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
