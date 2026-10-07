"""Explicit estimate jobs preserve the legacy IC and respect the observed cut."""

import sqlite3
from contextlib import closing
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import gabi.domain.research.factors as factor_lab
from gabi import config, storage
from gabi.application.errors import QueryError
from gabi.domain.research import estimates
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.estimates import run_estimate_analysis
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.estimates import SqliteEstimateAnalysis
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


def _unbounded(path, cutoff):
    """The retired module's own readers: every capture and the full price history, no observed cut."""
    import exchange_calendars as xcals

    def batches(period):
        with closing(sqlite3.connect(path)) as db:
            return pd.read_sql_query("SELECT captured_at, COUNT(DISTINCT symbol) AS n_symbols FROM estimate_snapshots "
                                     "WHERE period=? GROUP BY captured_at ORDER BY captured_at ASC", db, params=(period,))

    def rows(period, captures):
        with closing(sqlite3.connect(path)) as db:
            return pd.read_sql_query(
                "SELECT symbol, captured_at, revised_up_30d, revised_down_30d FROM estimate_snapshots "
                "WHERE period=? AND captured_at IN ({})".format(",".join("?" * len(captures))), db,
                params=[period, *captures])

    return estimates.evaluate_estimate_revision_signal(
        cutoff=cutoff, batch_loader=batches, snapshot_loader=rows,
        price_loader=lambda symbols, first, last: storage.get_prices_multi(symbols),
        sessions=lambda as_of, months: factor_lab._entry_exit_sessions(xcals.get_calendar("XNYS"), as_of, months),
        forward_returns=factor_lab._forward_returns)


def _seed(root, *, future=False):
    path = root / "gabi.db"
    captures = ["2024-01-03", "2024-01-18", "2024-02-02", "2024-02-20", "2024-03-06", "2024-03-21"]
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE estimate_snapshots (
                symbol TEXT, captured_at TEXT, period TEXT,
                revised_up_30d INTEGER, revised_down_30d INTEGER);
            CREATE TABLE prices (
                symbol TEXT, date TEXT, open REAL, high REAL, low REAL,
                close REAL, volume INTEGER, adj_close REAL);
        """)
        db.executemany("INSERT INTO estimate_snapshots VALUES (?,?,?,?,?)", [
            (f"S{i:02d}", f"{day}T12:00:00+00:00", "0q", i, 0)
            for day in captures for i in range(20)
        ])
        if future:
            db.executemany("INSERT INTO estimate_snapshots VALUES (?,?,?,?,?)", [
                (f"S{i:02d}", "2026-01-01T12:00:00+00:00", "0q", i, 0)
                for i in range(20)
            ])
        days = pd.date_range("2024-01-01", periods=180, freq="B")
        db.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)", [
            (f"S{i:02d}", day.date().isoformat(), price, price, price, price, 1, price)
            for i in range(20)
            for n, day in enumerate(days)
            for price in [100.0 * (1.0001 + i * 0.0001) ** n]
        ])
        db.commit()
    return path


def test_bounded_analysis_matches_legacy_formula_without_future_reads(tmp_path, monkeypatch):
    path = _seed(tmp_path, future=True)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", path)
    legacy = _unbounded(path, date(2025, 7, 2))
    after_legacy = path.read_bytes()
    bounded = run_estimate_analysis(tmp_path, date(2025, 7, 2))
    assert legacy["status"] == bounded["status"] == "ok"
    pd.testing.assert_frame_equal(legacy["summary"], bounded["summary"])
    pd.testing.assert_frame_equal(legacy["ic_series"], bounded["ic_series"])
    assert bounded["batches_available"] == 6
    assert path.read_bytes() == after_legacy
    with pytest.raises(QueryError, match="Solo se permite"):
        SqliteEstimateAnalysis(tmp_path, date(2025, 7, 2)).prices_for_sessions(
            ["S00"], "2025-07-02", "2025-07-03")


def test_estimate_job_requires_research_and_publishes_bounded_result(tmp_path, monkeypatch):
    path = _seed(tmp_path, future=True)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", path)
    request = {"kind": "estimate_analysis", "idempotency_key": "estimate-job-01"}
    with TestClient(create_app(Settings(tmp_path))) as api:
        denied = api.post("/api/v1/jobs", json=request)
        assert denied.status_code == 403
    assert not (tmp_path / "gabi_jobs.db").exists()
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    before = path.read_bytes()
    with TestClient(create_app(Settings(tmp_path))) as api:
        created = api.post("/api/v1/jobs", json=request)
        assert created.status_code == 202, created.text
        job_id = created.json()["id"]
        assert Worker(SqliteJobs(tmp_path), LegacyExecutor(Settings(tmp_path)), tmp_path).run_once()
        preview = api.get(f"/api/v1/research/estimate-analysis/{job_id}")
        assert preview.status_code == 200, preview.text
        result = preview.json()
        assert result["status"] == "ok"
        assert result["observed_cutoff"] == "2025-07-02"
        assert result["batches_available"] == 6
        assert result["summary"][0]["ic_mean"] == pytest.approx(1)
        assert result["independent_advantage_demonstrated"] is False
        full = api.get(f"/api/v1/jobs/{job_id}/result").json()
        assert len(full["ic_series"]) >= 6
        assert result["result_sha256"] == SqliteJobs(tmp_path).get(job_id)["result_sha256"]
    assert path.read_bytes() == before
    assert not (tmp_path / "gabi.db-wal").exists()
    (tmp_path / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with TestClient(create_app(Settings(tmp_path))) as api:
        assert api.get(f"/api/v1/jobs/{job_id}/result").status_code == 403
        assert api.get(f"/api/v1/research/estimate-analysis/{job_id}").status_code == 403
