"""Estimate coverage is honest, bounded, and has no read-side effects."""

import sqlite3
from contextlib import closing

from fastapi.testclient import TestClient

from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def _capture_db(root, *, batches=6, symbols=20):
    path = root / "gabi.db"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE estimate_snapshots (symbol TEXT, captured_at TEXT, period TEXT)")
        db.executemany("INSERT INTO estimate_snapshots VALUES (?,?,?)", [
            (f"S{symbol:02d}", f"2024-{month:02d}-01T12:00:00+00:00", "0q")
            for month in range(1, batches + 1) for symbol in range(symbols)
        ])
        db.execute("INSERT INTO estimate_snapshots VALUES (?,?,?)",
                   ("OTHER", "2024-07-01T12:00:00+00:00", "+1q"))
        db.commit()
    return path


def test_estimate_capture_status_counts_actual_batches_without_evaluation(tmp_path):
    path = _capture_db(tmp_path)
    before = path.read_bytes()
    with TestClient(create_app(Settings(tmp_path))) as client:
        response = client.get("/api/v1/research/estimate-captures")
    assert response.status_code == 200
    assert response.json() == {
        "period": "0q", "batches_total": 6, "batches_eligible": 6,
        "first_eligible": "2024-01-01T12:00:00+00:00",
        "last_eligible": "2024-06-01T12:00:00+00:00", "span_days": 152,
        "batches_needed": 6, "span_days_needed": 60, "symbols_per_batch_needed": 20,
        "history_threshold_met": True, "evaluation_status": "not_run",
        "independent_advantage_demonstrated": False,
    }
    assert path.read_bytes() == before
    assert not (tmp_path / "gabi.db-wal").exists()


def test_estimate_capture_status_distinguishes_sparse_batches(tmp_path):
    _capture_db(tmp_path, batches=6, symbols=19)
    with TestClient(create_app(Settings(tmp_path))) as client:
        result = client.get("/api/v1/research/estimate-captures").json()
    assert result["batches_total"] == 6
    assert result["batches_eligible"] == 0
    assert result["span_days"] == 0
    assert result["history_threshold_met"] is False


def test_estimate_capture_status_missing_db_does_not_create_it(tmp_path):
    absent = tmp_path / "absent"
    with TestClient(create_app(Settings(absent))) as client:
        response = client.get("/api/v1/research/estimate-captures")
    assert response.status_code == 200
    assert response.json()["batches_total"] == 0
    assert not absent.exists()


def test_estimate_capture_status_missing_table_does_not_create_it(tmp_path):
    path = tmp_path / "gabi.db"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE unrelated (value TEXT)")
    before = path.read_bytes()
    with TestClient(create_app(Settings(tmp_path))) as client:
        response = client.get("/api/v1/research/estimate-captures")
    assert response.status_code == 200
    assert response.json()["batches_total"] == 0
    assert path.read_bytes() == before


def test_estimate_capture_status_fails_closed_on_malformed_table(tmp_path):
    path = tmp_path / "gabi.db"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE estimate_snapshots (wrong_column TEXT)")
    with TestClient(create_app(Settings(tmp_path))) as client:
        response = client.get("/api/v1/research/estimate-captures")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "estimate_data_unavailable"
