"""Bounded synthetic F4 worker measurement; never reads repository data/."""

import ctypes
import os
import sqlite3
import threading
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from gabi.application.administration.jobs import JobCommand
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import quality_snapshot
from gabi.infrastructure.storage.jobs import SqliteJobs


def rss_bytes() -> int:
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong),
                        ("peak", ctypes.c_size_t), ("working", ctypes.c_size_t),
                        ("peak_pagefile", ctypes.c_size_t), ("pagefile", ctypes.c_size_t),
                        ("peak_pool_nonpaged", ctypes.c_size_t), ("pool_nonpaged", ctypes.c_size_t),
                        ("peak_pool_paged", ctypes.c_size_t), ("pool_paged", ctypes.c_size_t)]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise OSError("Cannot read process memory")
        return int(counters.working)
    # Linux current RSS; /proc is only used by this standalone measurement.
    line = next(row for row in Path("/proc/self/status").read_text().splitlines() if row.startswith("VmRSS:"))
    return int(line.split()[1]) * 1024


def fixture(root: Path) -> None:
    symbols = [f"S{number:04}" for number in range(1000)]
    (root / "sp500_constituents.csv").write_text("symbol\n" + "\n".join(symbols) + "\n")
    with closing(sqlite3.connect(root / "gabi.db")) as db, db:
        for table in ("prices", "fundamentals", "edgar_metrics"):
            db.execute(f"CREATE TABLE {table}(symbol TEXT)")
            db.execute(f"CREATE INDEX {table}_symbol ON {table}(symbol)")
            db.executemany(f"INSERT INTO {table} VALUES(?)", [(symbol,) for symbol in symbols])


def main() -> None:
    with TemporaryDirectory(prefix="gabi-jobs-measure-") as temporary:
        root = Path(temporary).resolve()
        fixture(root)
        store = SqliteJobs(root)
        store.enqueue(JobCommand("quality"), "measurement-quality", "test")
        baseline = rss_bytes()
        peak = baseline
        stop = threading.Event()

        def monitor() -> None:
            nonlocal peak
            while not stop.wait(0.005):
                peak = max(peak, rss_bytes())

        watcher = threading.Thread(target=monitor, daemon=True)
        tracemalloc.start()
        watcher.start()
        started = time.perf_counter()
        worker = Worker(store, lambda _: quality_snapshot(root), root)
        with ThreadPoolExecutor(max_workers=4) as pool:
            reads = [pool.submit(lambda: [store.list() for _ in range(20)]) for _ in range(3)]
            assert worker.run_once()
            assert all(task.result() for task in reads)
        elapsed = time.perf_counter() - started
        stop.set()
        watcher.join()
        _, heap_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result = store.list()[0]
        assert result["status"] == "succeeded"
        print(f"1000 symbols, 3 source tables, 60 parallel list reads + 1 worker: {elapsed:.3f}s")
        print(f"Working set before/peak: {baseline / 2**20:.1f}/{peak / 2**20:.1f} MiB")
        print(f"Python allocation peak during measurement: {heap_peak / 2**20:.1f} MiB")


if __name__ == "__main__":
    main()
