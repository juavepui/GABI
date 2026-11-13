"""Measure complete SEC selection/resolution/error operations on synthetic local rows."""

import ast
import json
import runpy
import sqlite3
import statistics
import tempfile
import time
import tracemalloc
from contextlib import closing, contextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from gabi.application.market.sec_cik import resolve
from gabi.application.market.sec_selection import batch, refresh
from gabi.infrastructure.storage.sec_cik import SqliteCikResolutions
from gabi.infrastructure.storage.sec_selection import SqliteSecSelection
from gabi.infrastructure.storage.sec_xbrl import SCHEMA
from gabi.infrastructure.storage.sync_events import SCHEMA as SYNC_SCHEMA

ROOT = Path(__file__).resolve().parents[1]


def main():
    fixture = runpy.run_path(str(ROOT / "backend/tests/test_sec_selection_migration.py"))
    pd, now, reference = fixture["pd"], fixture["NOW"], fixture["REFERENCE"]
    symbols = [f"S{i:05}" for i in range(250)]
    mapping = pd.DataFrame({"symbol": symbols[:225], "cik": [str(i + 1).zfill(10) for i in range(225)],
                            "title": [f"Issuer {i}" for i in range(225)]})
    samples = {mode: {name: [] for name in ("original", "migrated")}
               for mode in ("current_selection", "fresh_selection", "historical_selection")}
    with tempfile.TemporaryDirectory(prefix="sec_selection_measure_", dir=ROOT) as directory:
        for repeat in range(4):
            outputs: dict = {mode: {} for mode in samples}
            for name in ("original", "migrated"):
                path = Path(directory) / f"{name}_{repeat}.db"
                from gabi import identity
                with closing(sqlite3.connect(path)) as db:
                    db.executescript(SCHEMA + SYNC_SCHEMA)
                    identity.ensure_schema(db)
                    db.execute("CREATE TABLE cik_resolutions(symbol TEXT PRIMARY KEY,cik TEXT,title TEXT,resolved_at TEXT)")
                    for i, symbol in enumerate(symbols):
                        cik = str(i + 1).zfill(10)
                        db.execute("INSERT INTO edgar_metrics(symbol,cik,fetched_at) VALUES (?,?,?)",
                                   (symbol, cik, (now - timedelta(hours=48 if i >= 125 else 0)).isoformat()))
                        row = {"tag": "Revenues", "unit": "USD", "start_date": "2018-01-01",
                               "end_date": "2018-12-31", "val": 100., "form": "10-K", "fp": "FY", "fy": 2018,
                               "filed_date": "2019-02-01", "accn": str(i)}
                        db.execute("INSERT INTO edgar_facts VALUES (?,?,?,?,?,?,?,?,?,?,?)", (symbol, *row.values()))
                        db.execute("INSERT INTO entities VALUES (?,?,?,?)", (f"cik:{cik}", cik, None, "2010-01-01"))
                        db.execute("INSERT INTO entity_aliases VALUES (?,?,?,?,?,?)",
                                   (f"cik:{cik}", symbol, "2010-01-01", "2020-01-01", "synthetic", 1.))
                        identity.put_observations(db, f"cik:{cik}", "edgar_facts", symbol, [row], "synthetic://sec")
                        if i >= 225:
                            db.execute("INSERT INTO cik_resolutions VALUES (?,?,?,?)", (symbol, cik, f"Issuer {i}", now.isoformat()))
                        if i < 5:
                            db.execute("INSERT INTO sync_checkpoints VALUES ('sec',?,?,?)",
                                       (f"cik:{cik}", f"facts:{symbol}", json.dumps({"status": "failed"})))
                    db.commit()
                store, resolutions = SqliteSecSelection(path, lambda: now), SqliteCikResolutions(path, lambda: now)
                calls = []
                def runner(tasks, operation):
                    for symbol, cik in tasks:
                        operation(symbol, cik)
                        yield symbol, None
                def download(requested, ciks, **options):
                    calls.append((list(requested), dict(ciks), options))
                    return batch(requested, ciks, operation=lambda *a: None, runner=runner, classify_error=str)
                if name == "original":
                    @contextmanager
                    def connection():
                        with closing(sqlite3.connect(path)) as db:
                            with db:
                                yield db
                    namespace = {"pd": pd, "datetime": SimpleNamespace(now=lambda tz: now, fromisoformat=fixture["datetime"].fromisoformat),
                                 "UTC": fixture["UTC"], "timedelta": timedelta,
                                 "config": SimpleNamespace(EDGAR_CACHE_MAX_AGE_HOURS=24),
                                 "storage": SimpleNamespace(get_connection=connection),
                                 "_classify_error": lambda exc, **k: ("test", str(exc)), "resolve_cik": resolve,
                                 "get_cik_map": lambda **k: mapping, "fetch_edgar_batch": download}
                    for node in ast.parse(reference["edgar"]).body:
                        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {"SCHEMA", "FACTS_SCHEMA", "RESOLUTIONS_SCHEMA"} for t in node.targets):
                            exec(ast.get_source_segment(reference["edgar"], node), namespace)
                        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in {"get_edgar_fetched_at", "get_symbols_with_facts",
                            "_remember_cik_resolution", "_get_cached_cik_resolution", "_CikResolutions", "get_cik_for_symbol"}:
                            exec(ast.get_source_segment(reference["edgar"], node), namespace)
                    def failures(source):
                        with connection() as db:
                            return set(db.execute("SELECT entity,dataset FROM sync_checkpoints WHERE source=? "
                                                  "AND json_extract(state_json,'$.status')='failed'", (source,)))
                    namespace["sync_state"] = SimpleNamespace(failed_datasets=failures)
                    storage_ns = {"datetime": namespace["datetime"], "UTC": fixture["UTC"], "timedelta": timedelta,
                                  "get_connection": connection, "UPDATE_ERRORS_RETENTION_DAYS": 90}
                    schema = next(n for n in ast.parse(reference["storage"]).body if isinstance(n, ast.Assign)
                                  and any(isinstance(t, ast.Name) and t.id == "SCHEMA" for t in n.targets))
                    exec(ast.get_source_segment(reference["storage"], schema), storage_ns)
                    namespace["storage"].record_update_errors = fixture["captured"]("storage", "record_update_errors", storage_ns)
                    identity_ns = {"pd": pd, "json": json, "date": fixture["datetime"], "storage": namespace["storage"]}
                    for node in ast.parse(reference["identity"]).body:
                        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {"SCHEMA", "MIN_CONFIDENCE"} for t in node.targets):
                            exec(ast.get_source_segment(reference["identity"], node), identity_ns)
                        if isinstance(node, ast.FunctionDef) and node.name in {"ensure_schema", "normalize_symbol", "observations", "resolve"}:
                            exec(ast.get_source_segment(reference["identity"], node), identity_ns)
                    # All requested symbols have dated aliases, so historical_pit fallback is never used.
                    namespace["identity"] = SimpleNamespace(**identity_ns)
                    execute = fixture["captured"]("edgar", "ensure_edgar_data", namespace)
                else:
                    def execute(requested, **options):
                        return refresh(requested, store=store, mapping=lambda **k: mapping,
                            resolutions=resolutions, download_batch=download, classify_error=str, now=lambda: now,
                            default_max_age_hours=24, **options)
                for mode in samples:
                    if mode == "fresh_selection":
                        with closing(sqlite3.connect(path)) as db:
                            db.execute("UPDATE edgar_metrics SET fetched_at=?", (now.isoformat(),))
                            db.execute("DELETE FROM sync_checkpoints")
                            db.commit()
                    calls.clear()
                    actual = sqlite3.connect
                    counts = {"connections": 0, "selects": 0}
                    def trace(statement):
                        if statement.lstrip().upper().startswith("SELECT"):
                            counts["selects"] += 1
                    def connect(*args, **options):
                        counts["connections"] += 1
                        db = actual(*args, **options)
                        db.set_trace_callback(trace)
                        return db
                    sqlite3.connect = connect
                    tracemalloc.start()
                    started = time.perf_counter()
                    try:
                        result = execute(symbols, **({"as_of": "2019-06-01"} if mode == "historical_selection" else {}))
                        seconds = time.perf_counter() - started
                        _, peak = tracemalloc.get_traced_memory()
                    finally:
                        sqlite3.connect = actual
                        tracemalloc.stop()
                    samples[mode][name].append((seconds, peak / 1024**2, counts))
                    with closing(sqlite3.connect(path)) as db:
                        rows = db.execute("SELECT * FROM cik_resolutions ORDER BY symbol").fetchall()
                    outputs[mode][name] = result, list(calls), rows
            for values in outputs.values():
                assert values["original"] == values["migrated"]
    results = {mode: {name: {"first_seconds": values[0][0], "warm_median_seconds": statistics.median(v[0] for v in values[1:]),
                            "max_python_peak_mib": max(v[1] for v in values), "queries": values[-1][2]}
                      for name, values in names.items()} for mode, names in samples.items()}
    results.update(symbols=len(symbols), attributed_rows=len(symbols), downloads=0, warm_repeats=3,
                   parity="Selections, flags, errors and persistent CIK resolutions identical")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
