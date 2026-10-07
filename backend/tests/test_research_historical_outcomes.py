"""Later returns of a historical ranking use the legacy formula and never read reserved prices."""

import sqlite3
from contextlib import closing
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from ranking_fixture import RankingFixture

from gabi import config
from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError
from gabi.application.research.historical import build_historical_ranking
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi.infrastructure.storage.window_prices import SqliteWindowPrices
from gabi_api.bootstrap import create_app

SYMBOLS = [f"T{i:03d}" for i in range(12)]


def _prices(root):
    rng = np.random.default_rng(3)
    days = pd.bdate_range("2018-12-01", "2025-07-02")
    with closing(sqlite3.connect(root / "gabi.db")) as db:
        db.execute("CREATE TABLE prices (symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
                   "volume INTEGER, adj_close REAL)")
        for symbol in [*SYMBOLS, "SPY"]:
            if symbol == "T011":
                continue  # A symbol without prices must stay missing, never zero.
            path = 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(days)))
            db.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)", [
                (symbol, day.date().isoformat(), p, p, p, p, 1, None if (symbol == "T003" and i % 5 == 0) else p)
                for i, (day, p) in enumerate(zip(days, path))])
        db.commit()


def _ranking(as_of):
    rng = np.random.default_rng(5)
    table = pd.DataFrame({
        "name": [f"Empresa {s}" for s in SYMBOLS],
        "composite_score": [None if i == 1 else float(90 - i) for i in range(12)],
        "score_coverage": [0.4 if i == 2 else 0.8 for i in range(12)],
        **{column: rng.uniform(0, 100, 12) for column in ("value_score", "quality_score", "momentum_score",
                                                          "risk_score")},
    }, index=pd.Index(SYMBOLS, name="symbol"))
    return {"table": table, "universe_info": {"is_exact": True, "note": "fixture"}}


def test_window_reader_matches_legacy_lookup_and_refuses_reserved_dates(tmp_path, monkeypatch):
    _prices(tmp_path)
    evaluation = RankingFixture(tmp_path, date(2025, 7, 2))
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    reader = SqliteWindowPrices(tmp_path, date(2025, 7, 2))
    for symbol in ("T000", "T003", "T011", "SPY"):
        for target in ("2019-01-05", "2019-07-02", "2020-03-15", "2024-12-25"):
            for after in (False, True):
                ts = pd.Timestamp(target)
                assert reader(symbol, ts, after) == evaluation._adjusted_at(symbol, ts, after), (symbol, target)
    with pytest.raises(QueryError, match="observado"):
        reader("T000", pd.Timestamp("2025-06-28"), after=True)


def _jobs(tmp_path, as_of):
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    store = SqliteJobs(tmp_path)
    ranking = store.enqueue(JobCommand("historical_ranking", start=as_of), f"hist-{as_of}", "ui")
    assert Worker(store, lambda command: build_historical_ranking(command.start, _ranking), tmp_path).run_once()
    return store, ranking["id"]


def test_outcomes_job_repeats_streamlit_selection_and_formula(tmp_path, monkeypatch):
    _prices(tmp_path)
    evaluation = RankingFixture(tmp_path, date(2025, 7, 2))
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    store, ranking_id = _jobs(tmp_path, "2019-01-02")
    request = {"kind": "historical_outcomes", "idempotency_key": "outcomes-01",
               "outcomes": {"source_job_id": ranking_id, "top_n": 5, "cost_bps": 10}}
    with TestClient(create_app(Settings(tmp_path))) as api:
        created = api.post("/api/v1/jobs", json=request)
        assert created.status_code == 202, created.text
        assert Worker(store, LegacyExecutor(Settings(tmp_path)), tmp_path).run_once()
        response = api.get(f"/api/v1/research/historical-outcomes/{created.json()['id']}")
        assert response.status_code == 200, response.text
        data = response.json()

    df = _ranking("2019-01-02")["table"]
    eligible = df[df["composite_score"].notna()].head(5)
    assert data["candidates"] == eligible.index.tolist()
    for row, months in zip(data["horizons"], (6, 12)):
        expected = evaluation.evaluate(eligible.index.tolist(), "2019-01-02", months, 10)
        assert {key: row[key] for key in expected} == expected
    for row, (label, column) in zip(data["blocks"], (("Value", "value_score"), ("Quality", "quality_score"),
                                                    ("Momentum", "momentum_score"), ("Risk", "risk_score"))):
        leaders = df[df[column].notna() & (df["score_coverage"] >= .5)].nlargest(5, column)
        assert row["block"] == label and row["symbols"] == leaders.index.tolist()
        expected = evaluation.evaluate(leaders.index.tolist(), "2019-01-02", 12, 10)
        assert {key: row["outcome"][key] for key in expected} == expected
    assert data["independent_advantage_demonstrated"] is False


def test_outcomes_mark_reserved_horizons_without_reading_them(tmp_path, monkeypatch):
    _prices(tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    store, ranking_id = _jobs(tmp_path, "2024-12-02")
    with TestClient(create_app(Settings(tmp_path))) as api:
        created = api.post("/api/v1/jobs", json={
            "kind": "historical_outcomes", "idempotency_key": "outcomes-02",
            "outcomes": {"source_job_id": ranking_id, "top_n": 3}})
        assert Worker(store, LegacyExecutor(Settings(tmp_path)), tmp_path).run_once()
        data = api.get(f"/api/v1/research/historical-outcomes/{created.json()['id']}").json()
    six, twelve = data["horizons"]
    assert six["status"] in {"complete", "incomplete"} and six["end_date"] == "2025-06-02"
    assert twelve == {"months": 12, "status": "reserved", "end_date": "2025-12-02", "requested": 3,
                      "available": None, "portfolio_return": None, "benchmark_return": None,
                      "excess_return": None, "missing": []}
    assert all(block["outcome"]["status"] == "reserved" for block in data["blocks"])


def test_outcomes_require_research_and_valid_parameters(tmp_path):
    with TestClient(create_app(Settings(tmp_path))) as api:
        denied = api.post("/api/v1/jobs", json={"kind": "historical_outcomes", "idempotency_key": "outcomes-03",
                                                "outcomes": {"source_job_id": "a" * 32, "top_n": 5}})
        assert denied.status_code == 403
    with pytest.raises(QueryError):
        JobCommand("historical_outcomes", outcomes={"source_job_id": "a" * 32, "top_n": 0})
    with pytest.raises(QueryError):
        JobCommand("historical_outcomes", outcomes={"source_job_id": "a" * 32, "top_n": 5, "cost_bps": 500})
    with pytest.raises(QueryError):
        JobCommand("quality", outcomes={"source_job_id": "a" * 32, "top_n": 5})
