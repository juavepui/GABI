import json
import sqlite3
from datetime import UTC, datetime, time, timedelta

from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import edgar
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


def test_signals_read_is_inert_and_comparison_preserves_events(tmp_path):
    seed_fixture(tmp_path)
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as api:
        assert api.get("/api/v1/market/snapshots").json()["items"] == []
        assert api.get("/api/v1/market/signals").json()["items"] == []
        assert api.post("/api/v1/market/snapshots", json={"name": "  "}).status_code == 422
        snapshot = api.post("/api/v1/market/snapshots", json={"name": "Mi foto", "top_n": 5})
        assert snapshot.status_code == 201, snapshot.text
        snapshot_id = snapshot.json()["id"]
        assert snapshot.json()["candidates"] == 5
        with sqlite3.connect(tmp_path / "gabi.db") as db:
            db.execute("UPDATE ranking_snapshots SET score=score-40 WHERE snapshot_id=? AND rank=1", (snapshot_id,))
        first = api.post("/api/v1/market/signals/compare", json={"snapshot_id": snapshot_id})
        assert first.status_code == 200, first.text
        assert any(event["event_type"] == "score_change" for event in first.json()["items"])
        second = api.post("/api/v1/market/signals/compare", json={"snapshot_id": snapshot_id})
        assert second.status_code == 200
        saved = api.get("/api/v1/market/signals").json()["items"]
        assert len(saved) == len(first.json()["items"])
        assert api.post("/api/v1/market/signals/compare", json={"snapshot_id": 999999}).status_code == 404


def test_signals_missing_cache_does_not_initialize_tables(tmp_path):
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        assert api.get("/api/v1/market/snapshots").json()["items"] == []
        assert api.get("/api/v1/market/signals").json()["items"] == []
    assert not (tmp_path / "gabi.db").exists()


def test_cached_filings_job_and_earnings_preserve_signal_events(tmp_path):
    seed_fixture(tmp_path)
    with sqlite3.connect(tmp_path / "gabi.db") as db:
        db.executescript(edgar.FACTS_SCHEMA)
        info = json.loads(db.execute("SELECT info_json FROM fundamentals WHERE symbol='T000'").fetchone()[0])
        info["earningsTimestampStart"] = int(datetime.combine(TODAY + timedelta(days=3), time(), UTC).timestamp())
        info["isEarningsDateEstimate"] = True
        db.execute("UPDATE fundamentals SET info_json=? WHERE symbol='T000'", (json.dumps(info),))
        db.executemany("INSERT INTO edgar_facts "
                       "(symbol,tag,unit,start_date,end_date,val,form,fp,fy,filed_date,accn) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?)", [
                           ("T000", "Revenues", "USD", "2023-01-01", "2023-12-31", 100,
                            "10-K", "FY", 2023, "2024-02-01", "acc-2023"),
                           ("T000", "Revenues", "USD", "2024-01-01", "2024-12-31", 130,
                            "10-K", "FY", 2024, "2025-02-01", "acc-2024"),
                       ])
    settings = Settings(tmp_path)
    with TestClient(create_app(settings, today=lambda: TODAY)) as api:
        snapshot = api.post("/api/v1/market/snapshots", json={"name": "SEC", "top_n": 5}).json()
        snapshot_id = snapshot["id"]
        earnings = api.get(f"/api/v1/market/snapshots/{snapshot_id}/earnings")
        assert earnings.status_code == 200, earnings.text
        assert earnings.json()["items"] == [{"symbol": "T000", "event_date": "2026-10-02",
                                              "is_estimate": True, "days_until": 3}]
        queued = api.post("/api/v1/jobs", json={"kind": "filing_check",
                                                    "snapshot_id": snapshot_id,
                                                    "idempotency_key": "filing-check-1"})
        assert queued.status_code == 202, queued.text
        job_id = queued.json()["id"]
        assert api.post("/api/v1/market/signals/filings/record", json={"job_id": job_id}).status_code == 404
        assert Worker(SqliteJobs(tmp_path), LegacyExecutor(settings), tmp_path).run_once()
        job = api.get(f"/api/v1/jobs/{job_id}").json()
        assert job["status"] == "succeeded", job
        result = api.get(f"/api/v1/jobs/{job_id}/result").json()
        assert result["checked"] == 10
        event = next(item for item in result["events"] if item["symbol"] == "T000")
        assert event["event_type"] == "filing_revenue_improvement"
        assert api.get("/api/v1/market/signals").json()["items"] == []
        saved = api.post("/api/v1/market/signals/filings/record", json={"job_id": job_id})
        assert saved.status_code == 200, saved.text
        assert len(saved.json()["events"]) == 1
        api.post("/api/v1/market/signals/filings/record", json={"job_id": job_id})
        assert len(api.get("/api/v1/market/signals").json()["items"]) == 1
        with sqlite3.connect(tmp_path / "gabi.db") as db:
            assert db.execute("SELECT COUNT(*) FROM filing_comparisons WHERE symbol='T000'").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM filing_metadata WHERE symbol='T000'").fetchone()[0] == 2
