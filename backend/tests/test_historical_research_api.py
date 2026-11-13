"""Historical jobs preserve engine rows and never open reserved periods over HTTP."""

import math

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from gabi.application.research.historical import build_historical_ranking
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


def fixture_result(_as_of: str) -> dict:
    table = pd.DataFrame({
        "name": ["Empresa A", "Empresa B"], "sector": ["Industrials", None],
        "composite_score": [np.float64(78.5), np.nan], "score_coverage": [.9, .4],
        "identity_status": ["resolved", "unresolved"], "price": [125.0, np.nan],
        "source_note": ["point-in-time", "missing"],
        "sector_is_approximate": [np.bool_(False), np.bool_(True)],
    }, index=pd.Index(["AAA", "BBB"], name="symbol"))
    return {"table": table, "universe_info": {"is_exact": True, "source_date": "2019-01-02"}}


def test_historical_job_keeps_full_rows_and_read_only_preview(tmp_path):
    data = tmp_path / "data"
    store = SqliteJobs(data)
    with TestClient(create_app(Settings(data))) as api:
        created = api.post("/api/v1/jobs", json={
            "kind": "historical_ranking", "start": "2019-01-02",
            "idempotency_key": "historical-one",
        })
        assert created.status_code == 202, created.text
        job_id = created.json()["id"]
        worker = Worker(store, lambda command: build_historical_ranking(command.start, fixture_result), data)
        assert worker.run_once()
        full = api.get(f"/api/v1/jobs/{job_id}/result")
        assert full.status_code == 200, full.text
        assert full.json()["total"] == 2
        assert full.json()["rows"][0]["source_note"] == "point-in-time"
        assert full.json()["rows"][1]["composite_score"] is None
        assert full.json()["rows"][1]["sector_is_approximate"] is True
        assert full.json()["status"] == "RETROSPECTIVE_EXPLORATORY"
        preview = api.get(f"/api/v1/research/historical/{job_id}")
        assert preview.status_code == 200, preview.text
        assert preview.json()["rows"][0]["composite_score"] == 78.5
        assert preview.json()["universe_info"]["source_date"] == "2019-01-02"
        assert len(preview.json()["result_sha256"]) == 64
        assert api.get(f"/api/v1/research/historical/{'0' * 32}").status_code == 404
    assert math.isfinite(preview.json()["rows"][0]["composite_score"])


def test_historical_job_rejects_reserved_or_future_dates_before_writing(tmp_path):
    data = tmp_path / "data"
    with TestClient(create_app(Settings(data))) as api:
        for index, as_of in enumerate(("2009-12-31", "2026-01-01")):
            response = api.post("/api/v1/jobs", json={
                "kind": "historical_ranking", "start": as_of,
                "idempotency_key": f"reserved-{index}",
            })
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "reserved_period"
        assert api.post("/api/v1/jobs", json={
            "kind": "historical_ranking", "start": "2019-01-02", "end": "2020-01-02",
            "idempotency_key": "invalid-end",
        }).status_code == 422
    assert not data.exists()
