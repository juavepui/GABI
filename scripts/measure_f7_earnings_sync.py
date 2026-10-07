"""Whole synthetic EPS sync: original full-price reads vs bounded nearest-price reads."""
import argparse
import sqlite3
import statistics
import subprocess
import tempfile
import time
import tracemalloc
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd

from gabi.application.market.earnings_sync import sync_earnings_surprises
from gabi.infrastructure.legacy.earnings import YahooEarnings
from gabi.infrastructure.storage.earnings import SqliteEarnings

NOW = datetime(2024, 7, 30, 20, 30, tzinfo=UTC)


class FixedDate(date):
    @classmethod
    def today(cls):
        return NOW.date()


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def original(root, baseline, module):
    source = subprocess.check_output(["git", "show", f"{baseline}:backend/src/gabi/{module}.py"],
                                     cwd=root).decode("utf-8")
    result = ModuleType(f"gabi._measure_{module}")
    result.__package__ = "gabi"
    exec(compile(source, f"baseline-{module}", "exec"), result.__dict__)
    return result


def measured(call, repeats):
    times, peaks = [], []
    for _ in range(repeats):
        tracemalloc.start()
        start = time.perf_counter()
        assert call() == {}
        times.append(time.perf_counter() - start)
        peaks.append(tracemalloc.get_traced_memory()[1] / 1024**2)
        tracemalloc.stop()
    return statistics.median(times), max(peaks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="486942a")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--symbols", type=int, default=20)
    args = parser.parse_args()
    if min(args.symbols, args.repeats) < 1:
        parser.error("symbols and repeats must be positive")
    root = Path(__file__).resolve().parents[1]
    legacy, storage = original(root, args.baseline, "events_calendar"), original(root, args.baseline, "storage")
    symbols = [f"T{i:03d}" for i in range(args.symbols)]
    days = pd.bdate_range("2010-01-01", NOW.date())
    reports = pd.date_range("2019-01-30", periods=20, freq="3MS")
    history = pd.DataFrame({"EPS Estimate": 1., "Reported EPS": 1.1, "Surprise(%)": 10.}, index=reports)

    class SyntheticYahoo(YahooEarnings):
        @staticmethod
        def fetch(symbol):
            return history

    with tempfile.TemporaryDirectory(prefix="earnings_measure_", dir=root) as directory:
        folders = [Path(directory) / name for name in ("old", "new")]
        for folder in folders:
            folder.mkdir()
            with closing(sqlite3.connect(folder / "gabi.db")) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.executescript(storage.SCHEMA)
                db.executemany("INSERT INTO prices VALUES(?,?,?,?,?,?,?,?)", [
                    (symbol, day.date().isoformat(), value, value, value, value, 100, value)
                    for symbol in symbols for i, day in enumerate(days) for value in (100. + i / 10,)])
                db.commit()
        # Adapt only private baseline namespaces; operational global settings are untouched.
        storage.config = SimpleNamespace(DATA_DIR=folders[0], DB_PATH=folders[0] / "gabi.db")
        legacy.storage, legacy.date, legacy.datetime = storage, FixedDate, FixedDatetime
        legacy._fetch_earnings_history_attempt = lambda symbol: history
        store = SqliteEarnings(folders[1], now=lambda: NOW)

        def old():
            return legacy.sync_earnings_surprises(symbols)

        def new():
            return sync_earnings_surprises(symbols, SyntheticYahoo(), store, lambda exc: str(exc), today=NOW.date())

        old()
        new()
        before, after = measured(old, args.repeats), measured(new, args.repeats)
        with closing(sqlite3.connect(folders[0] / "gabi.db")) as db:
            expected = pd.read_sql_query("SELECT * FROM earnings_surprises ORDER BY symbol,earnings_date", db)
        with closing(sqlite3.connect(folders[1] / "gabi.db")) as db:
            actual = pd.read_sql_query("SELECT * FROM earnings_surprises ORDER BY symbol,earnings_date", db)
        pd.testing.assert_frame_equal(actual, expected)
        print(f"symbols={args.symbols} stored_sessions={len(days)} reports={len(reports)} repeats={args.repeats} exact_parity=True")
        for name, (seconds, peak) in (("old", before), ("new", after)):
            print(f"{name}: median_seconds={seconds:.4f} peak_python_mib={peak:.3f}")


if __name__ == "__main__":
    main()
