"""Synthetic isolated query parity and cold/warm allocation/SQL measurements."""

import ast
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
    from gabi.application.market.sec_reads import issuer_facts, metrics_as_of
    from gabi.domain.market import sec_facts
    from gabi.domain.market.sec_xbrl import normalize_cik
    from gabi.infrastructure.storage.sec_reads import SqliteSecReads

    reference = json.loads((ROOT / "backend/tests/fixtures/sec_reads_migration.json").read_text(encoding="utf-8"))
    results = {}
    with tempfile.TemporaryDirectory(prefix="gabi-sec-reads-") as directory:
        path = Path(directory) / "gabi.db"
        @contextmanager
        def connection():
            with closing(sqlite3.connect(path)) as db:
                yield db
        namespace = {**vars(sec_facts), "storage": SimpleNamespace(get_connection=connection), "pd": pd, "json": json, "date": date}
        names = {"FACTS_SCHEMA", "get_edgar_facts", "get_issuer_facts_as_of", "_facts_dict_from_stored", "compute_edgar_metrics_as_of"}
        for node in ast.parse(reference["edgar"]).body:
            if isinstance(node, ast.FunctionDef) and node.name in names or isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id in names for target in node.targets):
                code = ast.get_source_segment(reference["edgar"], node)
                code = code.replace("    from . import identity\n", "").replace("        from .identity import observations\n", "        observations = identity.observations\n")
                exec(code, namespace)
        def observations(entity, dataset):
            with connection() as db:
                rows = db.execute("SELECT symbol,payload_json FROM entity_observations WHERE entity_id=? AND dataset=? ORDER BY symbol,record_key", (entity, dataset)).fetchall()
            return pd.DataFrame([{**json.loads(payload), "source_symbol": symbol} for symbol, payload in rows])
        namespace["identity"] = SimpleNamespace(observations=observations, normalize_cik=normalize_cik, ensure_schema=lambda db: None)
        with connection() as db:
            db.executescript(namespace["FACTS_SCHEMA"])
            db.execute("CREATE TABLE entity_observations(entity_id TEXT,dataset TEXT,symbol TEXT,record_key TEXT,payload_json TEXT,source TEXT, PRIMARY KEY(entity_id,dataset,symbol,record_key))")
            for i in range(3000):
                year = 2016 + i % 10
                record = {"tag": "Revenues", "unit": "USD", "start_date": f"{year}-01-01", "end_date": f"{year}-12-31", "val": 100 + year - 2016,
                          "form": "10-K", "fp": "FY", "fy": year, "filed_date": f"{year+1}-02-01", "accn": str(i)}
                db.execute("INSERT INTO edgar_facts VALUES (?,?,?,?,?,?,?,?,?,?,?)", ("A", *(record[key] for key in ("tag", "unit", "start_date", "end_date", "val", "form", "fp", "fy", "filed_date", "accn"))))
                db.execute("INSERT INTO entity_observations VALUES (?,?,?,?,?,?)", ("cik:0000000001", "edgar_facts", "A", str(i), json.dumps(record), "https://sec.example/fact"))
            db.commit()
        reader = SqliteSecReads(path)
        flows = {
            "ticker_metrics": (lambda: namespace["compute_edgar_metrics_as_of"]("A", "2020-12-31"), lambda: metrics_as_of(reader, "A", "2020-12-31")),
            "issuer_metrics": (lambda: namespace["compute_edgar_metrics_as_of"]("A", "2020-12-31", entity_id="cik:0000000001"), lambda: metrics_as_of(reader, "A", "2020-12-31", entity_id="cik:0000000001")),
            "issuer_versions": (lambda: namespace["get_issuer_facts_as_of"]("1", "2020-12-31"), lambda: issuer_facts(reader, "1", "2020-12-31")),
        }
        actual_connect = sqlite3.connect
        for flow, pair in flows.items():
            outputs = []
            results[flow] = {}
            for label, execute in zip(("original", "migrated"), pair, strict=True):
                elapsed, peaks, counts = [], [], []
                for repeat in range(4):
                    count = {"connections": 0, "selects": 0, "rows": 0}
                    class MeasuredCursor:
                        def __init__(self, cursor):
                            self.cursor = cursor
                        def __getattr__(self, name):
                            return getattr(self.cursor, name)
                        def __iter__(self):
                            for row in self.cursor:
                                count["rows"] += 1
                                yield row
                        def fetchall(self):
                            rows = self.cursor.fetchall()
                            count["rows"] += len(rows)
                            return rows
                    class MeasuredConnection(sqlite3.Connection):
                        def cursor(self, *args, **kwargs):
                            return MeasuredCursor(super().cursor(*args, **kwargs))
                        def execute(self, *args, **kwargs):
                            return MeasuredCursor(super().execute(*args, **kwargs))
                    def connect(*args, **kwargs):
                        count["connections"] += 1
                        kwargs["factory"] = MeasuredConnection
                        db = actual_connect(*args, **kwargs)
                        db.set_trace_callback(lambda sql: count.__setitem__("selects", count["selects"] + 1) if sql.lstrip().upper().startswith("SELECT") else None)
                        return db
                    sqlite3.connect = connect
                    try:
                        tracemalloc.start()
                        started = time.perf_counter()
                        output = execute()
                        elapsed.append(time.perf_counter() - started)
                        peaks.append(tracemalloc.get_traced_memory()[1] / 1024**2)
                    finally:
                        tracemalloc.stop()
                        sqlite3.connect = actual_connect
                    counts.append(count)
                    outputs.append(output)
                results[flow][label] = {"cold_seconds": elapsed[0], "warm_median_seconds": statistics.median(elapsed[1:]), "max_python_mib": max(peaks), "sql": counts}
            for output in outputs[1:]:
                if isinstance(output, pd.DataFrame):
                    assert_frame_equal(outputs[0], output)
                else:
                    assert outputs[0] == output
        print(json.dumps({"rows_per_source": 3000, "downloads": 0, "warm_repeats": 3, "parity": "exact", "measurements": results}, indent=2))


if __name__ == "__main__":
    main()
