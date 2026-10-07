"""Compare complete isolated WIKI cache-to-SQL imports against captured original."""

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


def main() -> None:
    fixture = runpy.run_path(str(ROOT / "backend/tests/test_wiki_migration.py"))
    with tempfile.TemporaryDirectory(prefix="wiki_measure_", dir=ROOT) as temporary:
        directory = Path(temporary).resolve()
        directory.relative_to(ROOT)
        cache_dir = directory / "cache"
        cache_dir.mkdir()
        dates = fixture["pd"].bdate_range("2008-01-01", "2016-06-30").strftime("%Y-%m-%d")
        symbols = [f"S{index:03}" for index in range(20)]
        for symbol in symbols:
            data = [[symbol, day, 25, 26, 24, 25.5, 1000, 0, 1, 24] for day in dates]
            (cache_dir / f"{symbol}.json").write_text(json.dumps(fixture["payload"](data)), encoding="utf8")
        total_bytes = sum(path.stat().st_size for path in cache_dir.glob("*.json"))
        readings = {"original": [], "migrated": []}
        first = {}
        for repetition in range(4):
            outputs = {}
            for name in readings:
                db = directory / f"{name}_{repetition}.db"
                original = fixture["legacy"](cache_dir, db) if name == "original" else None
                cache = fixture["FileWikiCache"](cache_dir)
                tracemalloc.start()
                start = time.perf_counter()
                if name == "original":
                    result = original.import_cached()
                else:
                    with closing(sqlite3.connect(db)) as connection:
                        result = fixture["import_cached"](cache, fixture["SqliteHistoricalPrices"](connection))
                elapsed = time.perf_counter() - start
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                outputs[name] = result, fixture["read_database"](db)
                if repetition == 0:
                    first[name] = elapsed
                else:
                    readings[name].append((elapsed, peak / 1024**2))
            assert outputs["original"] == outputs["migrated"]
        result = {name: {"first_measured_seconds": first[name],
                         "median_seconds": statistics.median(row[0] for row in rows),
                         "max_python_peak_mib": max(row[1] for row in rows)} for name, rows in readings.items()}
        result.update(files=len(symbols), rows=len(dates) * len(symbols), cache_bytes=total_bytes,
                      warm_repeats=3, downloads=0, parity="Full metadata JSON, hashes, counts and ordered SQL rows identical")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
