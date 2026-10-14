"""Synthetic parity and timing of sync checkpoint reads, measured attempts and event queries."""

import json
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
# The retired sync_state names (F7.29) over the production stores, shared with the tests.
sys.path.insert(0, str(ROOT / "backend/tests"))
ENTITIES = 500


def main():
    import sync_checkpoints as sync_state

    from gabi import config

    reference = json.loads((ROOT / "backend/tests/fixtures/sync_state_migration.json").read_text(encoding="utf-8"))
    results = {}
    with tempfile.TemporaryDirectory(prefix="gabi-sync-") as directory:
        paths = {label: Path(directory) / label / "gabi.db" for label in ("anterior", "nuevo")}
        counters = {"connections": 0, "schema": 0}
        real_connect = sqlite3.connect

        def connect(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            counters["connections"] += 1
            db.set_trace_callback(lambda s: counters.__setitem__(
                "schema", counters["schema"] + s.lstrip().upper().startswith("CREATE")))
            return db

        def legacy(path):
            @contextmanager
            def get_connection():
                path.parent.mkdir(parents=True, exist_ok=True)
                with closing(sqlite3.connect(path, timeout=30)) as db:
                    db.execute("PRAGMA journal_mode=WAL")
                    yield db
            namespace = {"__name__": "captured_sync_state", "storage": SimpleNamespace(get_connection=get_connection)}
            exec(reference["sync_state"].replace("from . import storage", ""), namespace)
            return SimpleNamespace(**namespace)

        def workload(target):
            def run():
                for i in range(ENTITIES):
                    target.get("sec", f"cik:{i}", "facts")
                    target.Attempt("sec", f"cik:{i}", "facts").finish("failed" if i % 10 == 0 else "unchanged",
                                                                      state={"token": str(i)})
                return sorted(target.failed_datasets("sec")), len(target.events_since(0))
            return run

        variants = {"anterior": workload(legacy(paths["anterior"])), "nuevo": workload(sync_state)}
        sqlite3.connect = connect
        try:
            outputs, row = [], {}
            for label, run in variants.items():
                config.DB_PATH = paths[label]
                for key in counters:
                    counters[key] = 0
                began = time.perf_counter()
                outputs.append(run())
                cold = time.perf_counter() - began
                calls = dict(counters)
                tracemalloc.start()
                run()
                peak = tracemalloc.get_traced_memory()[1] / 2**20
                tracemalloc.stop()
                warm = []
                for _ in range(3):
                    began = time.perf_counter()
                    run()
                    warm.append(time.perf_counter() - began)
                row[label] = {"cold_s": round(cold, 4), "warm_median_s": round(statistics.median(warm), 4),
                              "peak_python_mib": round(peak, 2), **calls}
            assert outputs[0] == outputs[1]
            results["Checkpoints, intentos y eventos"] = row
        finally:
            sqlite3.connect = real_connect
    print(json.dumps({"entities": ENTITIES, "parity": True, "downloads": 0, "results": results},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
