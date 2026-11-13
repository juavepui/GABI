"""Compare bounded factor snapshot reads and original cache/hash reads."""

import hashlib
import json
import runpy
import statistics
import tempfile
import time
import tracemalloc
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    fixture = runpy.run_path(str(ROOT / "backend/tests/test_academic_factors_migration.py"))
    with tempfile.TemporaryDirectory(prefix="factor_measure_", dir=ROOT) as temporary:
        directory = Path(temporary).resolve()
        directory.relative_to(ROOT)
        rng = np.random.default_rng(34)
        frame = pd.DataFrame(rng.normal(.005, .02, (768, 6)), index=pd.date_range("1963-01-01", periods=768, freq="MS"),
                             columns=["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"])
        frame["RF"] = .001
        path = directory / "ff_factors.csv"
        frame.to_csv(path)
        old = fixture["original"]()
        old.config = types.SimpleNamespace(DATA_DIR=directory)
        old._download_zip_csv = lambda *args: (_ for _ in ()).throw(AssertionError("network"))
        cache = fixture["FileFactorCache"](directory)
        source = fixture["Source"]()

        def original_read():
            factors = old.fetch_ff_factors()
            return factors, hashlib.sha256(path.read_bytes()).hexdigest()

        def migrated_read():
            snapshot = fixture["prepare_factor_snapshot"](cache, source)
            return snapshot.factors, snapshot.source["sha256"]

        readings = {"original": [], "migrated": []}
        first = {}
        expected = original_read()
        for repetition in range(31):
            for name, run in (("original", original_read), ("migrated", migrated_read)):
                tracemalloc.start()
                start = time.perf_counter()
                actual, digest = run()
                elapsed = time.perf_counter() - start
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                pd.testing.assert_frame_equal(actual, expected[0])
                assert digest == expected[1]
                if repetition == 0:
                    first[name] = elapsed
                else:
                    readings[name].append((elapsed, peak / 1024**2))
        result = {name: {"first_measured_seconds": first[name],
                         "median_seconds": statistics.median(row[0] for row in rows),
                         "max_python_peak_mib": max(row[1] for row in rows)} for name, rows in readings.items()}
        result.update({"rows": len(frame), "columns": len(frame.columns), "cache_bytes": path.stat().st_size,
                       "repeats": 30, "downloads": source.calls, "parity": "All loaded values and exact-byte SHA-256 match"})
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
