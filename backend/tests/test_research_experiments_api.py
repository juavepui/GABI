"""Research Lab experiments are read in Research mode only, unchanged and without writes."""

import sqlite3
from contextlib import closing

import pandas as pd
from fastapi.testclient import TestClient

from gabi import config
from gabi import research_lab as rl
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(rl, "_current_git_commit", lambda: "abc1234")
    returns = pd.Series([0.01, -0.02, 0.03], index=pd.to_datetime(["2012-03-30", "2012-06-29", "2012-09-28"]))
    first = rl.log_experiment("GABI-MF-v1.0", "RESEARCH", False, family="v1", sharpe=0.5, n_positions=20,
                              rebalance="Quarterly", returns=returns, periods_per_year=4.0, n_periods=3,
                              data_fingerprint="fp-1", weights={"value": 0.3},
                              result={"backtest_job_id": "a" * 32})
    second = rl.log_experiment("GABI-MF-v2.0", "OUT_OF_SAMPLE", True, family="v2", sharpe=0.9,
                               notes="segunda")
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    return first, second


def test_experiment_list_matches_legacy_log_without_writing(tmp_path, monkeypatch):
    first, second = _seed(tmp_path, monkeypatch)
    legacy = rl.list_experiments()
    before = (tmp_path / "gabi.db").read_bytes()
    with TestClient(create_app(Settings(tmp_path))) as client:
        response = client.get("/api/v1/research/experiments")
        filtered = client.get("/api/v1/research/experiments", params={"family": "v2", "stage": "OUT_OF_SAMPLE"})
        paged = client.get("/api/v1/research/experiments", params={"offset": 1, "limit": 1})
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == legacy["id"].tolist() == [second, first]
    assert body["families"] == rl.list_families()
    assert [stage["id"] for stage in body["stages"]] == rl.STAGES
    for item, (_, row) in zip(body["items"], legacy.iterrows()):
        for key in ("model_id", "stage", "family", "sharpe", "git_commit", "rebalance"):
            assert item[key] == (None if pd.isna(row[key]) else row[key])
        assert item["hypothesis_registered"] == bool(row["hypothesis_registered"])
        assert item["has_returns"] == pd.notna(row["returns_json"])
    assert "returns_json" not in response.text
    assert [item["id"] for item in filtered.json()["items"]] == [second]
    assert paged.json()["total"] == 2 and [item["id"] for item in paged.json()["items"]] == [first]
    assert (tmp_path / "gabi.db").read_bytes() == before


def test_experiment_detail_matches_legacy_environment(tmp_path, monkeypatch):
    first, _ = _seed(tmp_path, monkeypatch)
    legacy = rl.get_experiment(first)
    with TestClient(create_app(Settings(tmp_path))) as client:
        response = client.get(f"/api/v1/research/experiments/{first}")
        missing = client.get("/api/v1/research/experiments/999")
    assert response.status_code == 200
    body = response.json()
    assert body["python_version"] == legacy["python_version"]
    assert body["env_fingerprint"] == legacy["env_fingerprint"]
    assert body["data_fingerprint"] == "fp-1"
    assert body["deps"] == [{"package": k, "version": v} for k, v in sorted(legacy["deps"].items())]
    assert body["weights"] == legacy["weights"]
    assert body["backtest_job_id"] == "a" * 32
    assert (body["returns_count"], body["returns_first"], body["returns_last"]) == (3, "2012-03-30", "2012-09-28")
    assert missing.status_code == 404


def test_experiments_require_research_mode_and_validate_stage(tmp_path, monkeypatch):
    first, _ = _seed(tmp_path, monkeypatch)
    with TestClient(create_app(Settings(tmp_path))) as client:
        assert client.get("/api/v1/research/experiments", params={"stage": "BOGUS"}).status_code == 422
        (tmp_path / "app_mode.json").write_text('{"mode":"INVESTOR"}')
        listing = client.get("/api/v1/research/experiments")
        detail = client.get(f"/api/v1/research/experiments/{first}")
    assert listing.status_code == detail.status_code == 403
    assert listing.json()["error"]["code"] == "research_required"


def test_missing_log_and_old_schema_are_read_without_creating_anything(tmp_path):
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    with TestClient(create_app(Settings(tmp_path))) as client:
        assert client.get("/api/v1/research/experiments").json()["items"] == []
    assert not (tmp_path / "gabi.db").exists()
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db:
        # Schema before research_lab._ensure_columns added the environment columns.
        columns = rl.SCHEMA.replace("    deps_json TEXT,\n", "").replace("    python_version TEXT,\n", "")
        columns = columns.replace("    env_fingerprint TEXT,\n", "").replace("    data_fingerprint TEXT,\n", "")
        db.executescript(columns)
        db.execute("INSERT INTO experiments (created_at, model_id, hypothesis_registered, stage) "
                   "VALUES ('2026-01-01', 'old', 0, 'RESEARCH')")
        db.commit()
    before = (tmp_path / "gabi.db").read_bytes()
    with TestClient(create_app(Settings(tmp_path))) as client:
        detail = client.get("/api/v1/research/experiments/1").json()
    assert detail["python_version"] is None and detail["deps"] == [] and detail["returns_count"] == 0
    assert (tmp_path / "gabi.db").read_bytes() == before
