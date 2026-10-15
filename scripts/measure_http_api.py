"""Current HTTP/ASGI baseline on temporary synthetic data; never opens operational data.

Includes routing, response validation, JSON serialization and in-process client
transport. Excludes TCP, browser rendering and controlled OS disk-cache flushing.
"""

import argparse
import builtins
import gc
import hashlib
import io
import json
import platform
import socket
import sqlite3
import statistics
import subprocess
import sys
import tracemalloc
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import requests
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/tests"))
sys.path.insert(0, str(ROOT / "scripts"))
from market_fixture import TODAY, seed_fixture  # noqa: E402
from measure_jobs import rss_bytes  # noqa: E402

from gabi.domain.market.model_policy import FROZEN_WEIGHTS  # noqa: E402
from gabi.infrastructure.settings import Settings  # noqa: E402
from gabi_api.bootstrap import create_app  # noqa: E402


def forbidden(*args, **kwargs):
    raise AssertionError("Measurement attempted a write, external connection or reserved-data read")


@contextmanager
def readonly_requests(root: Path, statements: list[str]):
    """Instrument SQL and prohibit application writes/network, including cached connections."""
    connect, file_open, io_open = sqlite3.connect, builtins.open, io.open
    socket_connect = socket.socket.connect

    def checked_open(original):
        def read(file, mode="r", *args, **kwargs):
            if any(char in mode for char in "wax+"):
                forbidden()
            return original(file, mode, *args, **kwargs)
        return read

    def authorize(action, table, column, *args):
        if action == sqlite3.SQLITE_READ and (
            (table == "blind_validation_periods" and column != "validation_id")
            or (table == "experiments" and column != "stage")
        ):
            return sqlite3.SQLITE_DENY
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                   sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_RECURSIVE}
        if action == sqlite3.SQLITE_PRAGMA and (
            (table == "data_version" and column is None)
            or (table == "query_only" and str(column).upper() == "ON")
            or (table == "table_info" and column == "prices")
        ):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    def observed_connect(database, *args, **kwargs):
        expected = (root / "gabi.db").as_uri() + "?mode=ro"
        if str(database) != expected or kwargs.get("uri") is not True:
            forbidden()
        connection = connect(database, *args, **kwargs)
        connection.set_authorizer(authorize)
        connection.set_trace_callback(statements.append)
        return connection

    def local_socket(sock, address):
        # AnyIO may use an internal socketpair; no IP connections are needed by TestClient.
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            forbidden()
        return socket_connect(sock, address)

    with ExitStack() as stack:
        stack.enter_context(patch("sqlite3.connect", observed_connect))
        stack.enter_context(patch("builtins.open", checked_open(file_open)))
        stack.enter_context(patch("io.open", checked_open(io_open)))
        stack.enter_context(patch.object(requests.Session, "request", forbidden))
        stack.enter_context(patch.object(socket.socket, "connect", local_socket))
        stack.enter_context(patch.object(socket.socket, "connect_ex", forbidden))
        for name in ("write_text", "write_bytes", "mkdir", "unlink", "rename", "replace"):
            stack.enter_context(patch.object(Path, name, forbidden))
        yield


def input_hashes(root: Path) -> dict[str, str]:
    # Small synthetic inputs only. SHM lock bookkeeping is not application data.
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.iterdir() if path.is_file() and not path.name.endswith("-shm")}


def stable(payload: dict) -> dict:
    return {key: value for key, value in payload.items()
            if key not in {"generated_at", "revision", "cache_hit"}}


def process_memory() -> int | None:
    try:
        return rss_bytes()
    except (OSError, StopIteration):
        return None


def measure(client, repository, statements, path):
    gc.collect()
    statements.clear()
    queries, rows = repository.query_count, repository.row_count
    rss_before = process_memory()
    tracemalloc.start()
    try:
        started = perf_counter()
        response = client.get(path)
        elapsed = perf_counter() - started  # Fully buffered response, including serialization.
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    rss_after = process_memory()
    assert response.status_code == 200, response.text
    payload = response.json()  # Client JSON parsing/validation below is outside the timer.
    return payload, {
        "seconds": elapsed, "peak_python_mib": peak / 2**20,
        "process_rss_before_mib": rss_before / 2**20 if rss_before is not None else None,
        "process_rss_after_mib": rss_after / 2**20 if rss_after is not None else None,
        "sql_statements": len(statements),
        "select_queries": sum(sql.lstrip().upper().startswith("SELECT") for sql in statements),
        "adapter_queries": repository.query_count - queries,
        "adapter_rows_returned": repository.row_count - rows,
        "response_bytes": len(response.content), "cache_hit": payload.get("cache_hit"),
    }


def run(companies: int, sessions: int, repetitions: int) -> dict:
    if not 1 <= companies <= 496 or not 253 <= sessions <= 5000 or not 1 <= repetitions <= 20:
        raise ValueError("companies: 1..496 (+4 special cases); sessions: 253..5000; repetitions: 1..20")
    samples: dict[str, list[dict]] = {}
    ranking_path = "/api/v1/ranking?hide_no_data=false&limit=500"
    company_path = "/api/v1/companies/T000?bars=100"
    filter_path = "/api/v1/ranking?hide_no_data=false&sectors=Financials&offset=1&limit=2"
    with TemporaryDirectory(prefix="gabi-http-measure-") as temporary:
        root = Path(temporary).resolve()
        universe = seed_fixture(root, companies, sessions, wal=True)
        # Explicit fixture writer, never supplied to the application; keep WAL alive across reads.
        with closing(sqlite3.connect(root / "gabi.db")) as writer:
            writer.execute("SELECT count(*) FROM prices").fetchone()
            before = input_hashes(root)
            price_rows = writer.execute("SELECT count(*) FROM prices").fetchone()[0]
            statements: list[str] = []
            app = create_app(Settings(root), today=lambda: TODAY, session=lambda: TODAY)
            repository = app.state.market.repository
            # Start AnyIO before prohibiting IP sockets: on Windows its event loop
            # implements socketpair with a loopback connection. Requests remain guarded.
            with TestClient(app) as client, readonly_requests(root, statements):
                def request(name, path):
                    payload, observation = measure(client, repository, statements, path)
                    samples.setdefault(name, []).append(observation)
                    return payload

                for _ in range(repetitions):
                    repository.close()
                    cold = request("ranking_cold", ranking_path)
                    assert cold["cache_hit"] is False
                    assert cold["total"] == len(universe) == len(cold["items"])
                    warm = request("ranking_warm", ranking_path)
                    assert warm["cache_hit"] is True and stable(cold) == stable(warm)
                    filtered = request("ranking_filtered_page", filter_path)
                    expected = [item for item in cold["items"] if item["sector"] == "Financials"]
                    assert filtered["cache_hit"] is True
                    assert filtered["total"] == len(expected) and filtered["items"] == expected[1:3]
                    expected_company = next(item for item in cold["items"] if item["symbol"] == "T000")
                    repository.close()
                    detail = request("company_cold", company_path)
                    assert detail["company"] == expected_company and len(detail["prices"]) == 100
                    detail_warm = request("company_warm", company_path)
                    assert stable(detail) == stable(detail_warm)
                    repository.close()
                    started = perf_counter()
                    repository.ranking(dict(FROZEN_WEIGHTS), TODAY)
                    prewarm_seconds = perf_counter() - started
                    prewarmed = request("ranking_prewarmed", ranking_path)
                    samples["ranking_prewarmed"][-1]["prewarm_seconds_without_tracemalloc"] = prewarm_seconds
                    assert prewarmed["cache_hit"] is True and stable(cold) == stable(prewarmed)

                assert input_hashes(root) == before
                # The only data mutation is this declared correction of the temporary fixture.
                writer.execute("UPDATE prices SET close=close*.5, adj_close=adj_close*.5 "
                               "WHERE symbol='T000' AND date=(SELECT MIN(date) FROM prices WHERE symbol='T000')")
                writer.commit()
                corrected_inputs = input_hashes(root)
                corrected = request("ranking_invalidated", ranking_path)
                assert corrected["cache_hit"] is False and corrected["revision"] != prewarmed["revision"]
                assert corrected["data"]["latest_price_date"] == cold["data"]["latest_price_date"]
                updated_company = next(item for item in corrected["items"] if item["symbol"] == "T000")
                assert updated_company["metrics"]["volatility"] != expected_company["metrics"]["volatility"]
                detail_corrected = request("company_after_correction", company_path)
                assert detail_corrected["company"] == updated_company
                repository.close()
                fresh = request("ranking_corrected_fresh", ranking_path)
                assert stable(corrected) == stable(fresh)
                assert input_hashes(root) == corrected_inputs

    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                            cwd=ROOT, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return {
        "schema_version": 1, "commit": commit, "tracked_worktree_dirty": dirty,
        "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256((ROOT / "backend/tests/market_fixture.py").read_bytes()).hexdigest(),
        "python": platform.python_version(), "platform": platform.platform(),
        "fixture": {"seed": 64, "today": TODAY.isoformat(), "companies": len(universe),
                    "sessions": sessions, "price_rows": price_rows, "wal": True},
        "repetitions": repetitions,
        "scope": "HTTP via TestClient/ASGI: routing, validation, serialization, buffered response; no TCP/browser",
        "cold_scope": "empty ranking cache, no prewarm; OS cache not flushed (fixture just written)",
        "memory_scope": "tracemalloc Python peak; separate process RSS endpoints, not sampled peak or per-request delta",
        "timing_scope": "tracemalloc and SQL authorizer/trace enabled; GC and client JSON parsing excluded",
        "comparison": "current baseline only; earlier F2 case-use/local-data timings are not directly comparable",
        "checks": {"exact_cold_warm_prewarmed_parity": True, "filter_page_parity": True,
                   "company_universe_metrics_equal": True, "historical_wal_correction_invalidates": True,
                   "latest_date_unchanged": True, "corrected_matches_fresh_calculation": True,
                   "get_inputs_unchanged": True, "network_and_sql_writes_blocked": True},
        "cases": {name: {"samples": values,
                         "median_seconds": statistics.median(row["seconds"] for row in values)}
                  for name, values in samples.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=int, default=496)
    parser.add_argument("--sessions", type=int, default=1250)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run(args.companies, args.sessions, args.repetitions)
    except ValueError as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
