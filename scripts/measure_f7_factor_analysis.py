"""Compare complete old/new Factor Lab jobs on the same bounded synthetic SQL reader."""

import gc
import statistics
import subprocess
import time
import tracemalloc
import types
from contextlib import closing
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from gabi.application.research.factor_engine import run_factor_analysis
from gabi.infrastructure.storage.factor_prices import SqliteFactorPrices

BASELINE = "486942af7a92bea5afa7ffec98983eeba701baad"
TODAY = date(2024, 6, 30)


class Inputs:
    def __init__(self, root):
        self.symbols = [f"T{i:03}" for i in range(50)]
        self.prices = SqliteFactorPrices(root)

    def membership(self, as_of):
        return {"symbols": self.symbols, "is_exact": True, "note": "synthetic reviewed membership"}

    @staticmethod
    def sample(symbols, maximum):
        return list(symbols)

    def ranking(self, as_of, symbols):
        return pd.DataFrame({"composite_score": [float(i) for i in range(len(symbols))],
                             "score_coverage": .9, "sector": ["Tech" if i % 2 else "Energy" for i in range(len(symbols))]}, index=symbols)


def measure(run):
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    result = run()
    elapsed = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1] / 1_048_576
    tracemalloc.stop()
    return result, elapsed, peak


def main():
    root = Path(__file__).resolve().parents[1]
    code = subprocess.check_output(["git", "show", f"{BASELINE}:backend/src/gabi/factor_lab.py"], cwd=root).decode("utf-8")
    legacy = types.ModuleType("gabi._factor_measurement_reference")
    legacy.__package__ = "gabi"
    exec(compile(code, "factor_lab.py", "exec"), legacy.__dict__)

    class FixedDate(date):
        @classmethod
        def today(cls):
            return TODAY

    legacy.date = FixedDate
    with TemporaryDirectory(prefix="_factor_measure_", dir=root) as directory:
        import sqlite3

        path = Path(directory)
        inputs = Inputs(path)
        dates = pd.bdate_range("2016-01-01", "2024-06-28")
        with closing(sqlite3.connect(path / "gabi.db")) as db:
            db.execute("CREATE TABLE prices(symbol TEXT,date TEXT,adj_close REAL,PRIMARY KEY(symbol,date))")
            for i, symbol in enumerate(inputs.symbols):
                db.executemany("INSERT INTO prices VALUES(?,?,?)", ((symbol, day.date().isoformat(),
                                100 + j * (.02 + i * .001) + (j % 13) * .1) for j, day in enumerate(dates)))
            db.commit()
        legacy.universe = types.SimpleNamespace(get_sp500_constituents_asof=inputs.membership)
        legacy.screener_asof = types.SimpleNamespace(build_ranking_as_of=lambda as_of, symbols: {"table": inputs.ranking(as_of, symbols)})
        options = {"months": 3, "factor_cols": ("composite_score",), "horizons_months": (1, 3, 6, 12)}
        def old():
            return legacy.run_factor_analysis("2023-01-02", "2023-07-02", price_loader=inputs.prices, **options)

        def new():
            return run_factor_analysis("2023-01-02", "2023-07-02", inputs=inputs, today=TODAY, **options)
        old(), new()  # Warm the same calendar and libraries before timing.
        old_times, new_times, old_peaks, new_peaks = [], [], [], []
        for _ in range(3):
            before, old_time, old_peak = measure(old)
            after, new_time, new_peak = measure(new)
            for name in ("summary", "ic_series", "quantile_returns", "turnover"):
                pd.testing.assert_frame_equal(before[name], after[name])
            assert before["skipped"] == after["skipped"]
            old_times.append(old_time)
            new_times.append(new_time)
            old_peaks.append(old_peak)
            new_peaks.append(new_peak)
        print(f"symbols=50 rebalances=2 horizons=4 stored_sessions={len(dates)} repeats=3 exact_parity=True")
        print(f"old median_seconds={statistics.median(old_times):.4f} python_peak_mib={max(old_peaks):.3f}")
        print(f"new median_seconds={statistics.median(new_times):.4f} python_peak_mib={max(new_peaks):.3f}")


if __name__ == "__main__":
    main()
