"""Exercise the benchmark's financial parity and isolation, never timing thresholds."""

import importlib.util
import socket
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def benchmark():
    path = Path(__file__).resolve().parents[2] / "scripts/measure_http_api.py"
    spec = importlib.util.spec_from_file_location("measure_http_api", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_http_measurement_parity_and_historical_invalidation(benchmark):
    report = benchmark.run(companies=2, sessions=253, repetitions=1)
    assert all(report["checks"].values())
    assert report["fixture"]["companies"] == 6
    cases = report["cases"]
    cold = cases["ranking_cold"]["samples"][0]
    warm = cases["ranking_warm"]["samples"][0]
    assert cold["cache_hit"] is False and warm["cache_hit"] is True
    assert cold["adapter_rows_returned"] > warm["adapter_rows_returned"]
    assert cold["response_bytes"] > 0 and cold["select_queries"] > 0


def test_measurement_guards_reject_mutations_network_and_reserved_columns(benchmark, tmp_path):
    benchmark.seed_fixture(tmp_path, companies=1, sessions=253)
    with benchmark.readonly_requests(tmp_path, []):
        with pytest.raises(AssertionError):
            (tmp_path / "weights.json").write_text("{}")
        with pytest.raises(AssertionError):
            with (tmp_path / "weights.json").open("w"):
                pass
        with pytest.raises(AssertionError):
            sqlite3.connect(tmp_path / "gabi.db")
        with socket.socket() as sock, pytest.raises(AssertionError):
            sock.connect(("203.0.113.1", 443))
        connection = sqlite3.connect((tmp_path / "gabi.db").as_uri() + "?mode=ro", uri=True)
        try:
            assert connection.execute("SELECT count(*) FROM prices").fetchone()[0] > 0
            for sql in ("UPDATE prices SET close=0", "CREATE TABLE forbidden(x)",
                        "SELECT symbols_json FROM blind_validation_periods", "SELECT returns_json FROM experiments",
                        "PRAGMA query_only=OFF", "ATTACH DATABASE ':memory:' AS extra"):
                with pytest.raises(sqlite3.DatabaseError):
                    connection.execute(sql)
        finally:
            connection.close()
