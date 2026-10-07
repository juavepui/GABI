"""Compare the complete synthetic Form 4 sync and persisted rows, without SEC calls."""

import concurrent.futures as cf
import json
import sqlite3
import statistics
import subprocess
import tempfile
import time
import tracemalloc
import types
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from gabi.application.market.insider_sync import InsiderAttempt, sync_insiders
from gabi.infrastructure.storage.insiders import SCHEMA, SqliteInsiders

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2024, 1, 10, 12, tzinfo=UTC)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


class Source:
    def __init__(self, rows):
        self.rows = rows

    def mapping(self):
        return {symbol: "0000000001" for symbol in self.rows}

    def resolve(self, symbol, mapping):
        return mapping[symbol]

    def fetch(self, symbol, cik):
        return self.rows[symbol]

    def attempts(self, ciks, max_workers):
        with cf.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetch, symbol, cik): symbol for symbol, cik in ciks.items()}
            for future in cf.as_completed(futures):
                yield InsiderAttempt(futures[future], rows=future.result())


def measured(call):
    tracemalloc.start()
    start = time.perf_counter()
    result = call()
    elapsed = time.perf_counter() - start
    peak = tracemalloc.get_traced_memory()[1] / 1024 ** 2
    tracemalloc.stop()
    return result, elapsed, peak


def rows(path):
    with closing(sqlite3.connect(path)) as db:
        return (db.execute("SELECT * FROM insider_transactions ORDER BY symbol,accn,line_no").fetchall(),
                db.execute("SELECT * FROM insider_fetch_meta ORDER BY symbol").fetchall())


def main():
    reference = json.loads((ROOT / "backend/tests/fixtures/insider_sync_migration.json").read_text(encoding="utf-8"))
    original_source = subprocess.check_output([
        "git", "show", "54c0fec965e7bb1d8a062e0090b34c9357b79753:backend/src/gabi/insider.py"], cwd=ROOT).decode("utf-8")
    original = types.ModuleType("gabi._insider_benchmark")
    original.__package__ = "gabi"
    exec(compile(original_source, "insider_benchmark", "exec"), original.__dict__)
    original.datetime = FixedDatetime
    symbols = [f"T{i:03}" for i in range(50)]
    transactions = {symbol: [reference["rows"][0] | {"symbol": symbol, "accn": f"a{j}", "line_no": j}
                             for j in range(20)] for symbol in symbols}
    source = Source(transactions)
    with tempfile.TemporaryDirectory(prefix="insider_measure_", dir=ROOT) as temporary:
        directory = Path(temporary)
        old_path, new_dir = directory / "old.db", directory / "new"
        new_dir.mkdir()

        @contextmanager
        def connection():
            with closing(sqlite3.connect(old_path, timeout=30)) as db:
                db.execute("PRAGMA journal_mode=WAL")
                yield db

        original.storage = types.SimpleNamespace(get_connection=connection, record_update_errors=lambda *args: None)
        original.edgar = types.SimpleNamespace(get_cik_map=source.mapping,
                                              get_cik_for_symbol=lambda symbol, cik_map: (source.resolve(symbol, cik_map), None))
        original.fetch_insider_transactions = source.fetch
        store = SqliteInsiders(new_dir, now=lambda: NOW)
        with connection() as db:
            db.executescript(SCHEMA)
            db.commit()
        with closing(sqlite3.connect(store.path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            db.commit()
        def old_call():
            return original.ensure_insider_data(symbols, max_age_hours=-1)

        def new_call():
            return sync_insiders(symbols, source, store, str, now=lambda: NOW, max_age_hours=-1)
        old_call()
        new_call()
        old_times, new_times, old_peaks, new_peaks = [], [], [], []
        for _ in range(3):
            old_result, old_time, old_peak = measured(old_call)
            new_result, new_time, new_peak = measured(new_call)
            assert old_result == new_result == {"refreshed": 50, "failed": {}}
            assert rows(old_path) == rows(store.path)
            old_times.append(old_time)
            new_times.append(new_time)
            old_peaks.append(old_peak)
            new_peaks.append(new_peak)
        print("symbols=50 transactions_per_symbol=20 repeats=3 exact_sql_parity=True")
        print(f"legacy_median_s={statistics.median(old_times):.4f} python_peak_mib={max(old_peaks):.3f}")
        print(f"new_median_s={statistics.median(new_times):.4f} python_peak_mib={max(new_peaks):.3f}")


if __name__ == "__main__":
    main()
