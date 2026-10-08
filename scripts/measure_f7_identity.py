"""Measure identity filing guards and canonical hashing on isolated synthetic data."""

import json
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from pandas.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))


def main():
    from gabi.application.market.identity import last_filings
    from gabi.application.research.historical_pit import ranking_series
    from gabi.domain.research.periods import P2010
    from gabi.infrastructure.storage.historical_pit import SqliteHistoricalPit
    from gabi.infrastructure.storage.identity import SqliteIdentityReads
    from gabi.infrastructure.storage.identity_writes import SqliteIdentityWrites, put_observations

    reference = json.loads((ROOT / "backend/tests/fixtures/identity_migration.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="gabi-identity-measure-") as directory:
        path = Path(directory) / "gabi.db"
        writer = SqliteIdentityWrites(path, lambda: date(2020, 1, 1), lambda: "unused")
        symbols = [f"S{i}" for i in range(200)]
        for index, symbol in enumerate(symbols, 1):
            owner = writer.ensure_entity(str(index))
            writer.add_alias(owner, symbol, "2016-01-01", source="synthetic")
            records = [{"tag": "Revenues", "unit": "USD", "start_date": "2018-01-01", "end_date": "2018-12-31",
                        "val": 100 + i, "form": "10-K", "fp": "FY", "fy": 2018,
                        "filed_date": "2019-02-01" if i % 2 else "2021-02-01", "accn": str(i)} for i in range(100)]
            with closing(sqlite3.connect(path)) as db:
                put_observations(db, owner, "edgar_facts", symbol, records, "synthetic")
                db.commit()

        @contextmanager
        def connection():
            with closing(sqlite3.connect(path)) as db:
                yield db

        def legacy_dates(values, as_of=None):
            assert not values
            return {}

        namespace = {"__name__": "gabi._measured_identity", "__package__": "gabi"}
        exec(reference["identity"].replace("    from . import edgar\n", ""), namespace)
        namespace["storage"] = SimpleNamespace(get_connection=connection)
        namespace["edgar"] = SimpleNamespace(get_last_filed_dates=legacy_dates)
        reader = SqliteIdentityReads(path)

        # A separate historical fixture keeps the core query's input unchanged.
        historical_path = Path(directory) / "historical.db"
        historical = {"__name__": "gabi._measured_historical_pit", "__package__": "gabi"}
        exec(reference["historical_pit"], historical)
        @contextmanager
        def historical_connection():
            with closing(sqlite3.connect(historical_path)) as db:
                yield db
        historical["storage"] = SimpleNamespace(get_connection=historical_connection)
        with historical_connection() as db:
            db.executescript(historical["historical_archive"].SCHEMA + historical["PROVENANCE_SCHEMA"])
            db.execute("INSERT INTO historical_price_provenance VALUES (?,?,?,?,?,?,?,?,?)",
                       ("cik:0000000001", "0000000001", "A", "2010-01-01", "2013-01-01", "fixture",
                        "split_and_dividend_adjusted", "tier_a", "[]"))
            days = pd.bdate_range("2010-01-01", "2012-12-31")
            db.executemany("INSERT INTO historical_prices VALUES (?,?,?,?,?,?,?,?,?,?)",
                           [("fixture", "A", day.date().isoformat(), 10., 10., 10., 10., 5., 1., "as_traded") for day in days])
            db.commit()
        historical_reader = SqliteHistoricalPit(historical_path)
        results = {"symbols": len(symbols), "facts": 20000, "downloads": 0, "measurements": {}}
        flows = {
            "last_filings": (lambda: namespace["last_filings"](symbols, "2020-01-01"),
                             lambda: last_filings(reader, symbols, "2020-01-01")),
            "attributed_fingerprint": (namespace["attributed_fingerprint"], reader.attributed_fingerprint),
            "accredited_ranking_series": (lambda: historical["ranking_series"]("cik:0000000001", "2012-03-30"),
                lambda: ranking_series(historical_reader, "cik:0000000001", "2012-03-30",
                    producers={P2010.price_producer}, quarter_ends=set(P2010.quarters), trailing_days=365)),
        }
        actual_connect = sqlite3.connect
        for name, pair in flows.items():
            results["measurements"][name] = {}
            outputs = []
            for label, execute in zip(("original", "migrated"), pair, strict=True):
                elapsed, peaks, counts = [], [], []
                for _ in range(4):
                    count = {"connections": 0, "selects": 0, "rows": 0}
                    class CountedCursor:
                        def __init__(self, cursor):
                            self.cursor = cursor
                        def __getattr__(self, key):
                            return getattr(self.cursor, key)
                        def __iter__(self):
                            for row in self.cursor:
                                count["rows"] += 1
                                yield row
                        def fetchall(self):
                            rows = self.cursor.fetchall()
                            count["rows"] += len(rows)
                            return rows
                        def fetchone(self):
                            row = self.cursor.fetchone()
                            count["rows"] += int(row is not None)
                            return row
                    class CountedConnection(sqlite3.Connection):
                        def cursor(self, *args, **kwargs):
                            return CountedCursor(super().cursor(*args, **kwargs))
                        def execute(self, *args, **kwargs):
                            return CountedCursor(super().execute(*args, **kwargs))
                    def connect(*args, **kwargs):
                        count["connections"] += 1
                        kwargs["factory"] = CountedConnection
                        db = actual_connect(*args, **kwargs)
                        db.set_trace_callback(lambda sql: count.__setitem__("selects", count["selects"] + 1)
                                              if sql.lstrip().upper().startswith("SELECT") else None)
                        return db
                    sqlite3.connect = connect
                    try:
                        tracemalloc.start()
                        started = time.perf_counter()
                        output = execute()
                        elapsed.append(time.perf_counter() - started)
                        peaks.append(tracemalloc.get_traced_memory()[1] / 1024 ** 2)
                        counts.append(count)
                    finally:
                        tracemalloc.stop()
                        sqlite3.connect = actual_connect
                outputs.append(output)
                results["measurements"][name][label] = {"cold_seconds": elapsed[0],
                    "warm_median_seconds": statistics.median(elapsed[1:]), "max_python_mib": max(peaks), "sql": counts}
            if isinstance(outputs[0], pd.DataFrame):
                assert_frame_equal(outputs[0], outputs[1])
                assert outputs[0].attrs == outputs[1].attrs
            else:
                assert outputs[0] == outputs[1], name
        results["parity"] = "exact"
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
