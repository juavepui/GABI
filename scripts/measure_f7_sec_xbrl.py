"""Measure issuer ingestion with complete persisted parity and synthetic SEC payloads."""

import json
import runpy
import sqlite3
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    fixture = runpy.run_path(str(ROOT / "backend/tests/test_sec_xbrl_migration.py"))
    samples = {mode: {name: [] for name in ("original", "migrated")}
               for mode in ("initial", "filings_hit", "revision")}
    count = 1500
    with tempfile.TemporaryDirectory(prefix="sec_xbrl_measure_", dir=ROOT) as temporary:
        for repeat in range(4):
            outputs: dict = {mode: {} for mode in samples}
            for name in ("original", "migrated"):
                service = fixture["original" if name == "original" else "modern"](Path(temporary) / f"{name}_{repeat}")
                for mode in samples:
                    facts = fixture["payload"](120 if mode == "revision" else 100, count=count)
                    service.source.fetch_company_facts = lambda cik: facts
                    service.source.companyfacts = service.source.fetch_company_facts
                    actual = sqlite3.connect
                    counts = {"connections": 0, "selects": 0}
                    def trace(statement):
                        if statement.lstrip().upper().startswith("SELECT"):
                            counts["selects"] += 1
                    def connect(*args, **kwargs):
                        counts["connections"] += 1
                        db = actual(*args, **kwargs)
                        db.set_trace_callback(trace)
                        return db
                    sqlite3.connect = connect
                    tracemalloc.start()
                    started = time.perf_counter()
                    try:
                        event = service.run("A", "1", full_refresh=mode == "revision")
                        seconds = time.perf_counter() - started
                        _, peak = tracemalloc.get_traced_memory()
                    finally:
                        tracemalloc.stop()
                        sqlite3.connect = actual
                    samples[mode][name].append((seconds, peak / 1024**2, counts))
                    outputs[mode][name] = event, fixture["read_tables"](service.path)
            for values in outputs.values():
                assert values["original"] == values["migrated"]
    results = {mode: {name: {"first_seconds": values[0][0],
                            "warm_median_seconds": statistics.median(v[0] for v in values[1:]),
                            "max_python_peak_mib": max(v[1] for v in values), "queries": values[-1][2]}
                      for name, values in names.items()} for mode, names in samples.items()}
    results.update(issuer_rows=count + 1, issuers=1, downloads=0, warm_repeats=3,
                   parity="All facts, attributed JSON/source, metrics, events and checkpoints identical")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
