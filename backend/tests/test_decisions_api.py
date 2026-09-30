"""Decision plans use existing calculations and never mutate data on GET."""

import pandas as pd
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import config, decision_engine
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


def test_decision_job_is_experimental_and_saved_in_legacy_table(tmp_path, monkeypatch):
    seed_fixture(tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    settings = Settings(tmp_path)
    app = create_app(settings, today=lambda: TODAY)
    with TestClient(app) as api:
        assert api.get("/api/v1/portfolio/decisions").json() == {"items": []}
        queued = api.post("/api/v1/jobs", json={
            "kind": "decision_plan", "idempotency_key": "decision-test-1",
            "decision_policy": {}, "holdings_text": "T000,3",
        })
        assert queued.status_code == 202, queued.text
        job_id = queued.json()["id"]
        early = api.post("/api/v1/portfolio/decisions", json={"job_id": job_id, "name": "Prueba"})
        assert early.status_code == 404
        assert api.get("/api/v1/portfolio/decisions").json() == {"items": []}
        assert Worker(SqliteJobs(tmp_path), LegacyExecutor(settings), tmp_path).run_once()
        finished = api.get(f"/api/v1/jobs/{job_id}").json()
        assert finished["status"] == "succeeded", finished
        result = api.get(f"/api/v1/jobs/{job_id}/result").json()
        assert result["status"] == "EXPERIMENTAL"
        assert result["holdings"] == {"T000": 3.0}
        assert result["model_id"]
        saved = api.post("/api/v1/portfolio/decisions", json={"job_id": job_id, "name": "Prueba"})
        assert saved.status_code == 201, saved.text
        plan_id = saved.json()["id"]
        assert saved.json()["decisions"] == result["decisions"]
        assert api.post("/api/v1/portfolio/decisions", json={"job_id": job_id, "name": "Otra"}).json()["id"] == plan_id
        assert decision_engine.load_saved_plan(plan_id).to_dict(orient="records") == result["decisions"]
        assert api.post(f"/api/v1/portfolio/decisions/{plan_id}/rename", json={"name": "Renombrado"}).json()["name"] == "Renombrado"
        assert api.get(f"/api/v1/portfolio/decisions/{plan_id}").json()["name"] == "Renombrado"
        assert api.post(f"/api/v1/portfolio/decisions/{plan_id}/delete").json()["deleted"] is True
        assert api.get(f"/api/v1/portfolio/decisions/{plan_id}").status_code == 404


def test_decisions_get_is_inert_and_invalid_holdings_do_not_save(tmp_path):
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as api:
        assert api.get("/api/v1/portfolio/decisions").json() == {"items": []}
        assert api.get("/api/v1/portfolio/decisions/1").status_code == 404
        assert not (tmp_path / "gabi.db").exists()
        assert not (tmp_path / "gabi_jobs.db").exists()
        queued = api.post("/api/v1/jobs", json={
            "kind": "decision_plan", "idempotency_key": "decision-test-2",
            "decision_policy": {}, "holdings_text": "T000,80\nT001,80",
        })
        assert queued.status_code == 202
        assert Worker(SqliteJobs(tmp_path), LegacyExecutor(Settings(tmp_path)), tmp_path).run_once()
        assert api.get(f"/api/v1/jobs/{queued.json()['id']}").json()["status"] == "failed"
        assert api.get("/api/v1/portfolio/decisions").json() == {"items": []}


def test_saved_plan_progress_matches_legacy_weighted_result(tmp_path, monkeypatch):
    seed_fixture(tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    rows = pd.DataFrame([
        {"symbol": "T000", "action": "COMPRAR", "current_pct": 0, "target_pct": 5,
         "change_pct": 5, "reason": "test", "score": 70},
        {"symbol": "T001", "action": "COMPRAR", "current_pct": 0, "target_pct": 2,
         "change_pct": 2, "reason": "test", "score": 68},
    ])
    plan_id = decision_engine.save_plan({"decisions": rows, "method": "legacy"}, decision_engine.Policy(), {})
    expected = decision_engine.plan_progress(plan_id)
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        response = api.get(f"/api/v1/portfolio/decisions/{plan_id}/progress")
        assert response.status_code == 200, response.text
        actual = response.json()
        assert actual["portfolio_return"] == expected["portfolio_return"]
        assert actual["benchmark_return"] == expected["benchmark_return"]
        assert actual["available"] == expected["available"]
        assert actual["missing"] == expected["missing"]
        assert actual["curve"]
