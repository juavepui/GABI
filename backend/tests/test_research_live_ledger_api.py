"""The prospective ledger in React: verified read-only queries, an explicit report job and evaluations."""

import json
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from test_live_ledger import NOW, decisions, panel, payload, seed, setup_capture

from gabi import config, live_performance
from gabi import live_ledger as ledger
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


@pytest.fixture(autouse=True)
def clock_and_research(monkeypatch):
    monkeypatch.setattr(ledger, "_now", lambda: NOW)
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("No network"))
    (config.DATA_DIR / "app_mode.json").write_text('{"mode":"RESEARCH"}')


def _files():
    """Every data file except SQLite's WAL index, which a read-only reader of a WAL database may create."""
    wal = config.DATA_DIR / "gabi.db-wal"
    assert not wal.exists() or wal.stat().st_size == 0  # Nothing was written through it.
    return {path.relative_to(config.DATA_DIR): path.read_bytes() for path in config.DATA_DIR.rglob("*")
            if path.is_file() and path.name not in {"app_mode.json", "gabi.db-wal", "gabi.db-shm"}}


def test_overview_and_replay_match_the_legacy_ledger_without_writing(monkeypatch):
    setup_capture(monkeypatch, panel())
    ledger.capture_current()
    ledger.append_decision(payload("NO_SIGNAL", []))
    expected_replay = ledger.reproduce_decision(1)
    expected = [event for event in ledger.events() if event["payload"]["kind"] == "DECISION"]
    before = _files()
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        overview = client.get("/api/v1/research/live-ledger").json()
        decision = client.get("/api/v1/research/live-ledger/decisions/1").json()
        event = client.get("/api/v1/research/live-ledger/decisions/1/event.json")
        assert client.get("/api/v1/research/live-ledger/decisions/9").status_code == 404
    assert overview["integrity"] == {"ok": True, "reason": None, "seq": 2, "broken_at": None}
    assert [row["seq"] for row in overview["decisions"]] == [e["seq"] for e in expected]
    assert overview["decisions"][1]["status"] == "NO_SIGNAL"
    assert overview["live_versions"] == sorted({e["payload"]["model_version"] for e in expected})
    assert decision["replay"] == {key: expected_replay[key] for key in (
        "fingerprint_matches", "scores_match", "ranking_matches", "replayed_top_n", "actual_top_n")}
    assert json.loads(event.content) == expected[0]
    assert _files() == before  # No lock file, schema, anchor or database change.


def test_tampered_anchor_is_reported_and_blocks_decisions():
    ledger.append_decision(payload())
    (config.DATA_DIR / "live_ledger" / "head.json").write_text('{"seq": 9, "hash": "x"}')
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        overview = client.get("/api/v1/research/live-ledger").json()
        decision = client.get("/api/v1/research/live-ledger/decisions/1")
    assert overview["integrity"]["ok"] is False and overview["decisions"] == []
    assert overview["integrity"]["reason"] == ledger.verify_integrity()["reason"]
    assert decision.status_code == 409


def test_cache_follows_new_events_and_missing_ledger_is_empty():
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        empty = client.get("/api/v1/research/live-ledger").json()
        assert empty["decisions"] == [] and empty["integrity"]["ok"]
        assert not (config.DATA_DIR / "gabi.db").exists() and not (config.DATA_DIR / "live_ledger").exists()
        ledger.append_decision(payload())
        assert [row["seq"] for row in client.get("/api/v1/research/live-ledger").json()["decisions"]] == [1]


def test_report_job_matches_live_performance_and_evaluation_is_appended_once(monkeypatch):
    decisions(monkeypatch)
    seed("A", [10, 12], [10, 12])
    seed("B", [12, 12], [12, 15])
    seed("SPY", [100, 105], [100, 110])
    expected = live_performance.report(model_version="model-v1")
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        job = client.post("/api/v1/jobs", json={"kind": "live_forward_report", "idempotency_key": "live-report-1",
                                                 "live_report": {"model_version": "model-v1"}}).json()
        assert Worker(SqliteJobs(config.DATA_DIR), LegacyExecutor(Settings(config.DATA_DIR)), config.DATA_DIR).run_once()
        report = client.get(f"/api/v1/research/live-forward/{job['id']}").json()
        saved = client.post("/api/v1/research/live-ledger/evaluations", json={"job_id": job["id"]})
        again = client.post("/api/v1/research/live-ledger/evaluations", json={"job_id": job["id"]})
    assert report["cumulative_return"] == expected["cumulative_return"]
    assert report["benchmark_return"] == expected["benchmark_return"]
    assert [row["net_return"] for row in report["intervals"]] == [row["net_return"] for row in expected["intervals"]]
    assert saved.status_code == 201 and again.status_code == 409
    last = ledger.events()[-1]
    assert last["seq"] == saved.json()["seq"] and last["payload"]["kind"] == "EVALUATION"
    assert last["payload"]["report_sha256"] == saved.json()["report_sha256"]
    assert ledger.verify_integrity()["ok"]


def test_ledger_requires_research_mode():
    ledger.append_decision(payload())
    (config.DATA_DIR / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        assert client.get("/api/v1/research/live-ledger").status_code == 403
        assert client.get("/api/v1/research/live-ledger/decisions/1").status_code == 403
        assert client.post("/api/v1/jobs", json={"kind": "live_forward_report", "idempotency_key": "live-report-2",
                                                 "live_report": {"model_version": "model-v1"}}).status_code == 403


def test_payload_tampering_is_reported(monkeypatch):
    ledger.append_decision(payload())
    with closing(sqlite3.connect(config.DATA_DIR / "gabi.db")) as db:
        db.execute("DROP TRIGGER live_ledger_no_update")
        db.execute("UPDATE live_ledger SET payload_json=replace(payload_json,'SIGNAL','NO_SIGNAL')")
        db.commit()
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        integrity = client.get("/api/v1/research/live-ledger").json()["integrity"]
    assert integrity == {"ok": False, "reason": "cadena modificada o con registros eliminados", "seq": None,
                         "broken_at": 1}
