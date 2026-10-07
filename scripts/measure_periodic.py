"""Compare the price-status read path with the last periodic_tasks revision, using temporary data only.

Run from the repository root: .venv/Scripts/python.exe scripts/measure_periodic.py
The legacy source comes from Git; neither operational data nor reserved studies are opened.
"""

import json
import sqlite3
import subprocess
import tempfile
import time
import tracemalloc
import types
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from gabi.application.administration.periodic import PeriodicTasks
from gabi.application.research.blind import BlindValidationQueries
from gabi.domain.market.freshness import last_completed_session
from gabi.infrastructure.storage.blind import SqliteBlindStore
from gabi.infrastructure.storage.periodic import PeriodicFiles

BASELINE = "9be44a8ab4bb3e70a33969eba08d8296028a9700"
NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


def main():
    source = subprocess.run(["git", "show", f"{BASELINE}:backend/src/gabi/periodic_tasks.py"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    legacy = types.ModuleType("gabi.periodic_benchmark")
    legacy.__package__ = "gabi"
    exec(compile(source, "<legacy periodic_tasks>", "exec"), legacy.__dict__)
    with tempfile.TemporaryDirectory(prefix="gabi-periodic-", dir=ROOT) as temporary:
        directory = Path(temporary)
        symbols = [f"S{i:04d}" for i in range(1000)]
        (directory / "sp500_constituents.csv").write_text("symbol\n" + "\n".join(symbols), encoding="utf-8")
        database = directory / "gabi.db"
        with closing(sqlite3.connect(database)) as db:
            db.execute("CREATE TABLE prices(symbol TEXT, date TEXT, adj_close REAL, PRIMARY KEY(symbol,date))")
            db.executemany("INSERT INTO prices VALUES(?,?,100)", [(s, "2024-01-10") for s in [*symbols, "SPY", "RSP"]])
            db.commit()
        store = PeriodicFiles(directory, directory / "tiingo", directory / "complete", directory / "result", "2027-01-15")
        blind = BlindValidationQueries(SqliteBlindStore(directory), lambda: NOW.date())
        # Status uses no write/source operations. They deliberately cannot be called here.
        service = PeriodicTasks(store, None, blind, lambda: NOW, time.perf_counter, time.process_time)  # type: ignore[arg-type]
        legacy.live_symbols = store.live_symbols
        legacy.blind_status = service.blind_status
        legacy.smallmid_state = store.smallmid_state
        legacy.tiingo_queue = store.tiingo_queue
        legacy.last_session = service.last_session
        counts = {"legacy": 0, "new": 0}
        original_connect = sqlite3.connect
        active = "legacy"

        @contextmanager
        def legacy_connection():
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
                yield db

        def connect(*args, **kwargs):
            connection = original_connect(*args, **kwargs)
            connection.set_trace_callback(lambda sql: counts.__setitem__(active, counts[active] + int(
                sql.upper().startswith("SELECT SYMBOL,MAX(DATE)") or sql.upper().startswith("SELECT MAX(DATE)"))))
            return connection

        last_completed_session(NOW)  # Warm the shared exchange calendar equally for both paths.
        with patch.object(legacy.storage, "get_connection", legacy_connection), patch.object(sqlite3, "connect", connect):
            results, reports = {}, {}
            for name, read in (("legacy", legacy.status), ("new", service.status)):
                active = name
                tracemalloc.start()
                elapsed = []
                for _ in range(2):
                    start = time.perf_counter()
                    reports[name] = read(NOW)
                    elapsed.append(time.perf_counter() - start)
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                results[name] = {"first_seconds": elapsed[0], "repeat_seconds": elapsed[1],
                                 "python_peak_mib": peak / 1024 ** 2, "price_queries_per_status": counts[name] // 2}
            if reports["legacy"] != reports["new"]:
                raise AssertionError("The status reports differ")
            print(json.dumps({"baseline": BASELINE, "symbols": len(symbols), "price_rows": len(symbols) + 2,
                              "equal_status": True, "measurements": results}, indent=2))


if __name__ == "__main__":
    main()
