"""The old Configuración: explicit data update with a failure summary and retry, and local API keys."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gabi import config, screener
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


@pytest.fixture
def client():
    with TestClient(create_app(Settings(config.DATA_DIR))) as test_client:
        yield test_client


def _run(client, update, key):
    job = client.post("/api/v1/jobs", json={"kind": "data_update", "idempotency_key": key, "update": update})
    assert job.status_code == 202, job.text
    assert Worker(SqliteJobs(config.DATA_DIR), LegacyExecutor(Settings(config.DATA_DIR)), config.DATA_DIR).run_once()
    return client.get(f"/api/v1/jobs/{job.json()['id']}/result").json()


def test_update_summarizes_failures_by_reason_and_retries_only_the_failed(client, monkeypatch):
    calls = []
    monkeypatch.setattr(screener, "get_universe",
                        lambda limit=None: pd.DataFrame({"symbol": ["AAA", "BBB", "CCC"][:limit or 3]}))

    def refresh(symbols, force=False, progress_cb=None, edgar_progress_cb=None):
        calls.append((symbols, force))
        for done in range(1, len(symbols) + 1):
            progress_cb(done, len(symbols), symbols[done - 1])
            edgar_progress_cb(done, len(symbols), symbols[done - 1])
        return {"price_refreshed": True, "fundamentals_refreshed": 1, "edgar_refreshed": 2,
                "failed": {"BBB": {"fundamentales": "límite de peticiones", "edgar": "sin CIK"},
                           "CCC": {"fundamentales": "límite de peticiones"}}}

    monkeypatch.setattr(screener, "refresh_data", refresh)
    first = _run(client, {"universe_limit": 50, "force": False}, "update-1")
    job_id = client.get("/api/v1/jobs").json()["jobs"][0]["id"]
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    phases = [event["message"] for event in job["events"]]
    assert "Fundamentales Yahoo: 3 de 3" in phases and "SEC EDGAR: 3 de 3" in phases
    assert phases.index("Fundamentales Yahoo: 1 de 3") < phases.index("SEC EDGAR: 3 de 3")
    assert calls[0] == (["AAA", "BBB", "CCC"], False)
    assert (first["symbols"], first["fundamentals_refreshed"], first["edgar_refreshed"]) == (3, 1, 2)
    assert first["failure_groups"] == [{"reason": "límite de peticiones", "symbols": ["BBB", "CCC"]},
                                       {"reason": "sin CIK", "symbols": ["BBB"]}]
    retry = _run(client, {"symbols": first["failed_symbols"], "force": False}, "update-2")
    assert calls[1] == (["BBB", "CCC"], True)  # «Reintentar solo los fallidos» forced the download.
    assert retry["retry"] is True


@pytest.mark.parametrize("update", [{"universe_limit": 75, "force": False},
                                    {"universe_limit": 50, "force": False, "symbols": ["AAA"]},
                                    {"symbols": ["bad symbol"], "force": True}])
def test_invalid_updates_are_rejected(client, update):
    response = client.post("/api/v1/jobs", json={"kind": "data_update", "idempotency_key": "update-bad",
                                                 "update": update})
    assert response.status_code == 422


def test_keys_are_saved_locally_and_never_returned(client):
    assert client.get("/api/v1/administration/settings").json()["keys"]["fred"] is False
    saved = client.post("/api/v1/administration/keys/fred", json={"key": "  secret-fred-key  "})
    assert saved.status_code == 200 and saved.json()["keys"]["fred"] is True
    assert "secret-fred-key" not in saved.text
    assert config.load_fred_key() == "secret-fred-key"
    assert client.post("/api/v1/administration/keys/fred", json={"key": "two words"}).status_code == 422
    assert client.post("/api/v1/administration/keys/other", json={"key": "x"}).status_code == 404


def test_key_writer_refuses_paths_outside_the_api_data_dir(client, monkeypatch, tmp_path):
    # Key paths are computed at import: a rebased DATA_DIR alone must not write the real key file.
    monkeypatch.setattr(config, "FRED_KEY_PATH", tmp_path / "elsewhere" / "fred_api_key.txt")
    response = client.post("/api/v1/administration/keys/fred", json={"key": "secret"})
    assert response.status_code == 503
    assert not (tmp_path / "elsewhere").exists()
