"""Measure original/new annual reports using the same temporary synthetic cache."""

import contextlib
import io
import json
import runpy
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    fixture = runpy.run_path(str(ROOT / "backend/tests/test_historical_data_audit_migration.py"))
    results: dict[str, list[dict]] = {"original": [], "migrated": []}
    with tempfile.TemporaryDirectory(prefix="annual_measure_", dir=ROOT) as temporary:
        directory = Path(temporary).resolve()
        directory.relative_to(ROOT)
        db, membership, detail = fixture["make_inputs"](directory)
        _, original = fixture["original_modules"]()

        def migrated():
            with contextlib.closing(fixture["connect_readonly"](db)) as connection:
                return fixture["audit"](fixture["reader_for"](connection, membership, detail))

        cases = {"original": lambda: original.audit(db, membership, detail), "migrated": migrated}
        with contextlib.redirect_stdout(io.StringIO()):
            reference = cases["original"]()
            cases["migrated"]()
            for _ in range(3):
                for name, case in cases.items():
                    tracemalloc.start()
                    start = time.perf_counter()
                    frame = case()
                    elapsed = time.perf_counter() - start
                    _, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    pd.testing.assert_frame_equal(frame, reference)
                    assert frame.to_csv(index=False) == reference.to_csv(index=False)
                    results[name].append({"seconds": elapsed, "python_peak_mib": peak / 1024**2})
        summary = {name: {"median_seconds": statistics.median(row["seconds"] for row in rows),
                          "max_python_peak_mib": max(row["python_peak_mib"] for row in rows)}
                   for name, rows in results.items()}
        summary.update({"years": len(reference), "columns": len(reference.columns), "repeats": 3,
                        "parity": "All values, column order and CSV text identical; no network, holdout or local data"})
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
