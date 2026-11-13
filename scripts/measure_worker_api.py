"""Bounded API/worker measurement with a synthetic Yahoo source and temporary SQLite.

The worker is a separate process. No operational data, external sources or research jobs.
"""

import argparse
import hashlib
import json
import multiprocessing as mp
import platform
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import tracemalloc
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/tests"))
sys.path.insert(0, str(ROOT / "scripts"))
from market_fixture import TODAY, seed_fixture  # noqa: E402
from measure_jobs import rss_bytes  # noqa: E402

from gabi.application.market.market_downloads import universe_data  # noqa: E402
from gabi.infrastructure.jobs.worker import Worker  # noqa: E402
from gabi.infrastructure.legacy.jobs import quality_snapshot  # noqa: E402
from gabi.infrastructure.settings import Settings  # noqa: E402
from gabi.infrastructure.storage.cache_writes import SqliteCacheWrites  # noqa: E402
from gabi.infrastructure.storage.jobs import SqliteJobs  # noqa: E402
from gabi_api.bootstrap import create_app  # noqa: E402

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)


def no_network(*args, **kwargs):
    raise AssertionError("External network forbidden in this measurement")


def execute_worker(directory, delay, ready, release, results):
    root = Path(directory)
    metrics = {"select_queries": 0, "sql_statements": 0, "price_rows_written": 0,
               "fundamentals_written": 0, "provider_seconds": 0.0, "storage_seconds": 0.0}
    connect = sqlite3.connect

    def observed(*args, **kwargs):
        connection = connect(*args, **kwargs)

        def trace(sql):
            metrics["sql_statements"] += 1
            metrics["select_queries"] += int(sql.lstrip().upper().startswith("SELECT"))
        connection.set_trace_callback(trace)
        return connection

    writes = SqliteCacheWrites(root / "gabi.db", lambda: NOW)
    symbols = pd.read_csv(root / "sp500_constituents.csv")["symbol"].tolist()

    def sync_prices(requested):
        for offset in range(0, len(requested), 25):
            started = time.perf_counter()
            time.sleep(delay)  # Explicit simulated provider latency, separate from local cost.
            frame = pd.DataFrame({"Open": [100.], "High": [102.], "Low": [99.], "Close": [101.],
                                  "Volume": [100000.], "Adj Close": [100.]}, index=pd.to_datetime([TODAY]))
            metrics["provider_seconds"] += time.perf_counter() - started
            started = time.perf_counter()
            for symbol in requested[offset:offset + 25]:
                writes.prices(symbol, frame)
                metrics["price_rows_written"] += 1
            metrics["storage_seconds"] += time.perf_counter() - started
        return {"failed": {}, "events": [{"skipped": False}]}

    def fundamentals(requested):
        started = time.perf_counter()
        time.sleep(delay)
        metrics["provider_seconds"] += time.perf_counter() - started
        started = time.perf_counter()
        for symbol in requested:
            writes.fundamentals(symbol, {"marketCap": 2e9, "trailingPE": 15., "returnOnEquity": .12}, None, None)
            metrics["fundamentals_written"] += 1
        metrics["storage_seconds"] += time.perf_counter() - started
        return {}

    def execute(command, progress):
        progress(0, "Proveedor simulado")
        ready.set()
        if not release.wait(30):
            raise RuntimeError("Measurement coordination timed out")
        started = time.perf_counter()
        if command.kind == "quality":
            result = quality_snapshot(root)
        else:
            result = universe_data(symbols, benchmark="SPY", max_age_hours=24, force=True, full_refresh=False,
                                   sync_prices=sync_prices, fundamentals_fetched_at=lambda _: {},
                                   failed_fundamentals=set, now=lambda: NOW, fetch_fundamentals=fundamentals,
                                   record_errors=writes.update_errors)
        metrics["execute_seconds"] = time.perf_counter() - started
        progress(1, "Operación terminada")
        return result

    execute.reports_progress = True
    stop = threading.Event()
    initial_rss = rss_bytes() / 2**20
    memory = {"rss_before_mib": initial_rss, "rss_peak_sampled_mib": initial_rss}

    def monitor():
        while not stop.wait(.005):
            memory["rss_peak_sampled_mib"] = max(memory["rss_peak_sampled_mib"], rss_bytes() / 2**20)

    watcher = threading.Thread(target=monitor, daemon=True)
    try:
        with patch("sqlite3.connect", observed), patch.object(socket.socket, "connect", no_network), \
                patch.object(socket.socket, "connect_ex", no_network):
            tracemalloc.start()
            watcher.start()
            started = time.perf_counter()
            assert Worker(SqliteJobs(root), execute, root).run_once()
            metrics["worker_seconds_including_coordination"] = time.perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
            memory["python_peak_mib"] = peak / 2**20
            tracemalloc.stop()
        results.put({"metrics": metrics, "memory": memory})
    except BaseException as exc:
        ready.set()
        results.put({"error": repr(exc)})
    finally:
        stop.set()
        watcher.join(timeout=2)


def market_state(root):
    with closing(sqlite3.connect((root / "gabi.db").as_uri() + "?mode=ro", uri=True)) as db:
        # Only the known synthetic tables, in a stable order; never hash an operational DB.
        return {table: hashlib.sha256(repr(db.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall()).encode()).hexdigest()
                for table in ("prices", "fundamentals", "edgar_metrics")}


def scenario(kind, concurrent, companies, sessions, delay):
    context = mp.get_context("spawn")
    with TemporaryDirectory(prefix="gabi-worker-api-") as directory:
        root = Path(directory)
        universe = seed_fixture(root, companies, sessions, wal=True)
        # Initialize command-side schema before GET measurements.
        SqliteCacheWrites(root / "gabi.db", lambda: NOW).initialize()
        with TestClient(create_app(Settings(root), today=lambda: TODAY, session=lambda: TODAY)) as api:
            assert api.get("/api/v1/ranking?limit=10").status_code == 200
            job = api.post("/api/v1/jobs", json={"kind": kind, "idempotency_key": "measurement-job"}).json()
            before = market_state(root)
            ready, release, results = context.Event(), context.Event(), context.Queue()
            process = context.Process(target=execute_worker, args=(directory, delay, ready, release, results))
            process.start()
            reads = []
            try:
                assert ready.wait(30), "Worker did not start"
                repository = api.app.state.market.repository
                if concurrent:
                    initial_job = api.get(f"/api/v1/jobs/{job['id']}").json()
                    assert initial_job["status"] == "running" and initial_job["result_ref"] is None
                    release.set()
                    for _ in range(3):
                        for path in ("/api/v1/jobs", "/api/v1/ranking?limit=10"):
                            rows, queries = repository.row_count, repository.query_count
                            started = time.perf_counter()
                            response = api.get(path)
                            seconds = time.perf_counter() - started
                            assert response.status_code in {200, 409}, response.text
                            reads.append({"path": path, "seconds": seconds, "status": response.status_code,
                                          "adapter_rows": repository.row_count - rows,
                                          "adapter_queries": repository.query_count - queries,
                                          "response_bytes": len(response.content)})
                            status = api.get(f"/api/v1/jobs/{job['id']}").json()
                            if status["status"] != "succeeded":
                                assert status["result_ref"] is None
                                # It can finish between the status and result reads.
                                assert api.get(f"/api/v1/jobs/{job['id']}/result").status_code in {404, 200}
                else:
                    release.set()
                observation = results.get(timeout=60)
                assert "error" not in observation, observation
                process.join(timeout=10)
                assert process.exitcode == 0
                completed = api.get(f"/api/v1/jobs/{job['id']}").json()
                assert completed["status"] == "succeeded", completed
                response = api.get(f"/api/v1/jobs/{job['id']}/result")
                assert response.status_code == 200
                artifact = root / "jobs/results" / f"{job['id']}.json"
                raw = artifact.read_bytes()
                assert hashlib.sha256(raw).hexdigest() == completed["result_sha256"]
                assert not list(artifact.parent.glob("*.tmp"))
                final_ranking = api.get("/api/v1/ranking?limit=10").json()["items"]
                after = market_state(root)
                if kind == "quality":
                    assert before == after
                return observation | {"concurrent_reads": reads, "artifact_bytes": len(raw),
                                      "result": response.json(), "market_hashes": after,
                                      "final_ranking": final_ranking, "companies": len(universe)}
            finally:
                release.set()
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
                results.close()


def run(companies=496, sessions=320, delay=.005):
    if not 1 <= companies <= 496 or not 253 <= sessions <= 1250 or not 0 <= delay <= .1:
        raise ValueError("companies: 1..496; sessions: 253..1250; provider delay: 0..0.1 seconds")
    cases = {}
    for kind in ("refresh", "quality"):
        serial = scenario(kind, False, companies, sessions, delay)
        concurrent = scenario(kind, True, companies, sessions, delay)
        for field in ("result", "market_hashes", "final_ranking"):
            assert serial[field] == concurrent[field], (kind, field)
            serial.pop(field)
            concurrent.pop(field)
        cases[kind] = {"serial": serial, "concurrent": concurrent}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    return {"commit": commit, "python": platform.python_version(), "platform": platform.platform(),
            "fixture": {"seed": 64, "companies": companies + 4, "sessions": sessions,
                        "price_rows": (companies + 3) * sessions + 5, "provider_delay_seconds_per_batch": delay},
            "scope": "separate worker process; real queue, market use case/cache writes, quality audit, HTTP via ASGI",
            "limits": "one sample per scenario; no TCP/browser or real network; refresh excludes macro/SEC/universe discovery; "
                      "worker seconds include synchronization; RSS sampled every 5 ms, Python peak separate",
            "checks": {"serial_concurrent_exact_parity": True, "atomic_artifact_sha256": True,
                       "quality_reads_only": True, "no_external_network": True}, "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=int, default=496)
    parser.add_argument("--sessions", type=int, default=320)
    parser.add_argument("--provider-delay", type=float, default=.005)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.companies, args.sessions, args.provider_delay)
    rendered = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
