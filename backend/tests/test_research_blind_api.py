"""Blind status stays read-only and cannot expose reserved observations."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date

from fastapi.testclient import TestClient

from gabi.domain.research.blind import canonical_payload
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def _seed(root):
    path = root / "gabi.db"
    payload = canonical_payload("2026-07-01", ["SECRET"], {"SECRET": 100.0})
    digest = hashlib.sha256(payload.encode()).hexdigest()
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE blind_validations (
              id INTEGER PRIMARY KEY, name TEXT, status TEXT, start_date TEXT,
              unlock_date TEXT, rebalance_months INTEGER);
            CREATE TABLE blind_validation_periods (
              validation_id INTEGER, rebalance_date TEXT, symbols_json TEXT,
              entry_prices_json TEXT, prev_hash TEXT, record_hash TEXT);
        """)
        db.execute("INSERT INTO blind_validations VALUES (1,?,?,?,?,?)",
                   ("Test", "locked", "2026-07-01", "2027-09-17", 3))
        db.execute("INSERT INTO blind_validation_periods VALUES (?,?,?,?,?,?)",
                   (1, "2026-07-01", json.dumps(["SECRET"]), json.dumps({"SECRET": 100.0}),
                    None, digest))
        db.commit()
    return path


def test_blind_status_is_sealed_read_only_and_matches_legacy_hash(tmp_path):
    db_path = _seed(tmp_path)
    before = db_path.read_bytes()
    with TestClient(create_app(Settings(tmp_path), today=lambda: date(2026, 9, 30))) as client:
        response = client.get("/api/v1/research/blind-validations")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item == {"id": 1, "name": "Test", "status": "locked", "unlock_date": "2027-09-17",
                    "n_periods": 1, "next_rebalance_due": "2026-10-01", "days_to_unlock": 352,
                    "integrity": {"ok": True, "broken_at": None, "n_periods": 1}, "revealed": False}
    assert "SECRET" not in response.text
    assert "100.0" not in response.text
    assert db_path.read_bytes() == before
    assert not (tmp_path / "gabi.db-wal").exists()


def test_blind_status_reports_tampering_without_revealing_positions(tmp_path):
    path = _seed(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE blind_validation_periods SET entry_prices_json=?", ('{"SECRET":999.0}',))
        db.commit()
    with TestClient(create_app(Settings(tmp_path), today=lambda: date(2026, 9, 30))) as client:
        response = client.get("/api/v1/research/blind-validations")
    assert response.status_code == 200
    assert response.json()["items"][0]["integrity"] == {
        "ok": False, "broken_at": "2026-07-01", "n_periods": 1}
    assert "SECRET" not in response.text
    assert "999" not in response.text


def test_blind_status_empty_database_does_not_initialize_schema(tmp_path):
    absent = tmp_path / "absent"
    with TestClient(create_app(Settings(absent))) as client:
        assert client.get("/api/v1/research/blind-validations").json() == {"items": []}
    assert not absent.exists()


def test_blind_status_fails_closed_on_excess_periods(tmp_path):
    path = _seed(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        db.executemany("INSERT INTO blind_validation_periods VALUES (?,?,?,?,?,?)",
                       [(1, f"2025-01-{(i % 28) + 1:02d}", "[]", "{}", None, "x")
                        for i in range(100)])
        db.commit()
    with TestClient(create_app(Settings(tmp_path))) as client:
        response = client.get("/api/v1/research/blind-validations")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "blind_data_limit"
