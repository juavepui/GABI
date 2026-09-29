import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from gabi.application.administration.jobs import JobCommand
from gabi.infrastructure.jobs.worker import Worker, process_lock
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


def client(tmp_path):
    return TestClient(create_app(Settings(tmp_path)))


def create_job(api, kind="quality", key="request-one", **options):
    return api.post("/api/v1/jobs", json={"kind": kind, "idempotency_key": key, **options})


def test_reads_do_not_initialize_jobs_and_api_never_exposes_keys_or_paths(tmp_path):
    (tmp_path / "fred_api_key.txt").write_text("private-key")
    with client(tmp_path) as api:
        assert api.get("/api/v1/jobs").json() == {"jobs": []}
        result = api.get("/api/v1/administration/settings")
        assert result.json()["keys"]["fred"] is True
        assert "private-key" not in result.text
        assert str(tmp_path) not in result.text
        assert not (tmp_path / "gabi_jobs.db").exists()


def test_research_weights_save_is_explicit_atomic_and_investor_is_locked(tmp_path):
    weights = {"value": 0.25, "quality": 0.25, "momentum": 0.25, "risk": 0.25}
    with client(tmp_path) as api:
        assert api.post("/api/v1/administration/weights", json=weights).status_code == 403
        assert not (tmp_path / "weights.json").exists()
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    with client(tmp_path) as api:
        invalid = weights | {"risk": 0.50}
        assert api.post("/api/v1/administration/weights", json=invalid).status_code == 422
        assert not (tmp_path / "weights.json").exists()
        response = api.post("/api/v1/administration/weights", json=weights)
        assert response.status_code == 200
        assert response.json()["status"] == "EXPERIMENTAL"
        assert api.get("/api/v1/model").json()["weights"] == weights
        assert json.loads((tmp_path / "weights.json").read_text()) == weights
        assert not list(tmp_path.glob("weights.*.tmp"))


def test_idempotency_conflict_cancel_and_result_publication(tmp_path):
    with client(tmp_path) as api:
        created = create_job(api).json()
        job_id = created["id"]
        assert created["status"] == "queued"
        assert create_job(api).json()["id"] == job_id
        assert create_job(api, kind="refresh").status_code == 409
        assert create_job(api, key="request-two").status_code == 409
        assert api.get(f"/api/v1/jobs/{job_id}/result").status_code == 404
        assert api.post(f"/api/v1/jobs/{job_id}/cancel").json()["status"] == "cancelled"
        assert create_job(api, key="request-three").status_code == 202
        store = SqliteJobs(tmp_path)
        assert Worker(store, lambda _: {"coverage": 3}, tmp_path).run_once()
        completed = api.get("/api/v1/jobs").json()["jobs"][0]
        assert completed["status"] == "succeeded"
        assert api.get(f"/api/v1/jobs/{completed['id']}/result").json() == {"coverage": 3}
        artifact = (tmp_path / "jobs" / "results" / f"{completed['id']}.json").read_bytes()
        assert hashlib.sha256(artifact).hexdigest() == completed["result_sha256"]
        (tmp_path / "jobs" / "results" / f"{completed['id']}.json").write_text("{}")
        assert api.get(f"/api/v1/jobs/{completed['id']}/result").status_code == 503


def test_two_workers_one_claim_and_stale_process_becomes_failed(tmp_path):
    store = SqliteJobs(tmp_path)
    store.enqueue(JobCommand("quality"), "first-key", "ui")
    token = "process-one"
    first = store.claim(token)
    assert first and first["status"] == "running"
    assert store.claim("process-two") is None
    with store.connection(write=True) as db:
        db.execute("UPDATE jobs SET lease_until=? WHERE id=?",
                   ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), first["id"]))
    assert store.claim("process-two") is None
    assert store.get(first["id"])["error_code"] == "worker_interrupted"
    assert not store.finish(first["id"], token, "succeeded", ref=first["id"], digest="bad")
    assert store.get(first["id"])["result_ref"] is None


def test_os_lock_excludes_a_second_worker_process(tmp_path):
    store = SqliteJobs(tmp_path)
    job = store.enqueue(JobCommand("quality"), "lock-test", "ui")
    with process_lock(tmp_path) as acquired:
        assert acquired
        assert not Worker(store, lambda _: {"ok": True}, tmp_path).run_once()
        assert store.get(job["id"])["status"] == "queued"
    assert Worker(store, lambda _: {"ok": True}, tmp_path).run_once()


def test_running_cancellation_and_failed_execution_never_publish(tmp_path):
    store = SqliteJobs(tmp_path)
    job = store.enqueue(JobCommand("symbols", ("SPY",)), "symbols-one", "ui")

    def cancelled(_):
        store.cancel(job["id"])
        return {"should_not_publish": True}

    assert Worker(store, cancelled, tmp_path).run_once()
    assert store.get(job["id"])["status"] == "cancelled"
    assert not (tmp_path / "jobs" / "results" / f"{job['id']}.json").exists()
    second = store.enqueue(JobCommand("quality"), "quality-two", "ui")

    def fails(_):
        raise RuntimeError("secret value and local path")

    Worker(store, fails, tmp_path).run_once()
    failed = store.get(second["id"])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "job_failed"
    assert "secret" not in json.dumps(failed)


def test_parallel_idempotent_requests_create_one_row(tmp_path):
    store = SqliteJobs(tmp_path)

    def submit(_):
        return store.enqueue(JobCommand("quality"), "same-request", "ui")["id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(submit, range(8)))) == 1
    assert len(store.list()) == 1


def test_job_validation_blocks_arbitrary_paths_and_scheduler_only_ops(tmp_path):
    with client(tmp_path) as api:
        assert create_job(api, kind="symbols", symbols=["../../secret"]).status_code == 422
        assert create_job(api, kind="symbols", symbols=[]).status_code == 422
        assert create_job(api, kind="backtest", start="2019-01-01", end="2026-01-01").status_code == 422
        assert api.post("/api/v1/jobs", json={"kind": "maintenance", "idempotency_key": "maintenance-1"}).status_code == 422


def test_separate_worker_process_and_scheduler_share_persistent_queue(tmp_path):
    (tmp_path / "sp500_constituents.csv").write_text("symbol\nSPY\nRSP\n")
    with sqlite3.connect(tmp_path / "gabi.db") as db:
        db.execute("CREATE TABLE prices(symbol TEXT)")
        db.execute("CREATE TABLE fundamentals(symbol TEXT)")
        db.execute("INSERT INTO prices VALUES('SPY')")
    settings = os.environ | {"GABI_DATA_DIR": str(tmp_path)}
    with client(tmp_path) as api:
        job_id = create_job(api).json()["id"]
    subprocess.run([sys.executable, "-m", "gabi_cli", "worker", "--once"], env=settings, check=True)
    with client(tmp_path) as api:
        assert api.get(f"/api/v1/jobs/{job_id}").json()["status"] == "succeeded"
        report = api.get(f"/api/v1/jobs/{job_id}/result").json()
        assert report["sources"]["prices"] == {"covered": 1, "total": 2}
        assert report["sources"]["fundamentals"] == {"covered": 0, "total": 2}
    for _ in range(2):
        subprocess.run([sys.executable, "-m", "gabi_cli", "schedule", "daily"], env=settings, check=True)
    assert sorted(job["kind"] for job in SqliteJobs(tmp_path).list()) == ["maintenance", "quality", "refresh"]


def test_legacy_writer_refuses_an_alternate_data_directory(tmp_path):
    with pytest.raises(RuntimeError, match="mismo directorio"):
        LegacyExecutor(Settings(tmp_path))(JobCommand("refresh"))
    assert not (tmp_path / "gabi.db").exists()
