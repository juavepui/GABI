"""Blind rebalances, revealed performance and exports run as Research jobs under the preregistered rules."""

from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_blind_validation import WEIGHTS, _fake_ranking, _seed_prices

from gabi import blind_validation as bv
from gabi import config
from gabi import research_lab as rl
from gabi.application.administration.periodic import PeriodicTasks
from gabi.application.research.blind import run_performance
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app

TODAY = date.today()


@pytest.fixture(autouse=True)
def research(monkeypatch):
    monkeypatch.setattr(bv, "_current_git_commit", lambda: "abc1234")
    monkeypatch.setattr(rl, "_current_git_commit", lambda: "abc1234")
    (config.DATA_DIR / "app_mode.json").write_text('{"mode":"RESEARCH"}')


def _run(client, kind, validation_id, key):
    job = client.post("/api/v1/jobs", json={"kind": kind, "idempotency_key": key,
                                             "blind": {"validation_id": validation_id}})
    assert job.status_code == 202, job.text
    worker = Worker(SqliteJobs(config.DATA_DIR), LegacyExecutor(Settings(config.DATA_DIR)), config.DATA_DIR)
    assert worker.run_once()
    return job.json()["id"]


def _prices(days=12):
    dates = pd.date_range(end=pd.Timestamp(TODAY), periods=days, freq="D")
    _seed_prices(dates, [("A", [100.0 + i for i in range(days)]), ("B", [50.0 + i for i in range(days)]),
                         ("SPY", [400.0 + i for i in range(days)])])
    return dates


def test_due_rebalance_is_recorded_once_without_revealing_positions(monkeypatch):
    _prices()
    _fake_ranking(monkeypatch, {"A": 90, "B": 80})
    monkeypatch.setattr(PeriodicTasks, "prices_fresh", lambda self: True)
    vid = bv.create_validation("Test", WEIGHTS, 2, 3, (TODAY - timedelta(days=1)).isoformat(), "2099-01-01")
    with TestClient(create_app(Settings(config.DATA_DIR), today=lambda: TODAY)) as client:
        first = client.get(f"/api/v1/research/blind-rebalances/{_run(client, 'blind_rebalance', vid, 'blind-r-1')}")
        again = client.get(f"/api/v1/research/blind-rebalances/{_run(client, 'blind_rebalance', vid, 'blind-r-2')}")
    assert first.json()["recorded"] and first.json()["n_positions"] == 2
    assert first.json()["rebalance_date"] == TODAY.isoformat()
    # Job IDs and hashes can contain the digits of a fixture price by chance.
    # The public payload must contain only these metadata fields, never positions/prices.
    assert set(first.json()) == {"job_id", "validation_id", "recorded", "reason",
                                "rebalance_date", "n_positions", "record_hash"}
    assert first.json()["reason"] is None
    assert bv.verify_integrity(vid) == {"ok": True, "broken_at": None, "n_periods": 1}
    assert again.json()["recorded"] is False and "próximo rebalanceo" in again.json()["reason"]


def test_stale_prices_block_the_rebalance(monkeypatch):
    _prices()
    _fake_ranking(monkeypatch, {"A": 90, "B": 80})
    monkeypatch.setattr(PeriodicTasks, "prices_fresh", lambda self: False)
    vid = bv.create_validation("Test", WEIGHTS, 2, 3, (TODAY - timedelta(days=1)).isoformat(), "2099-01-01")
    with TestClient(create_app(Settings(config.DATA_DIR), today=lambda: TODAY)) as client:
        result = client.get(f"/api/v1/research/blind-rebalances/{_run(client, 'blind_rebalance', vid, 'blind-r-3')}")
    assert result.json()["recorded"] is False and "precios" in result.json()["reason"]
    assert bv.verify_integrity(vid)["n_periods"] == 0


def test_revealed_performance_and_export_match_the_streamlit_page(monkeypatch):
    dates = _prices()
    _fake_ranking(monkeypatch, {"A": 90, "B": 80})
    vid = bv.create_validation("Test", WEIGHTS, 2, 1, dates[0].date().isoformat(), TODAY.isoformat())
    bv.record_rebalance(vid, as_of=dates[2].date().isoformat())
    bv.record_rebalance(vid, as_of=dates[6].date().isoformat())
    expected = pd.DataFrame(bv.get_status(vid)["performance"]["periods"])
    expected["capital"] = (1 + expected["retorno"].fillna(0)).cumprod()  # app/pages/13_Blind_Validation.py
    expected["capital_spy"] = (1 + expected["retorno_spy"].fillna(0)).cumprod()
    with TestClient(create_app(Settings(config.DATA_DIR), today=lambda: TODAY)) as client:
        performance = client.get(f"/api/v1/research/blind-performance/"
                                 f"{_run(client, 'blind_performance', vid, 'blind-p-1')}").json()
        exported = client.get(f"/api/v1/research/blind-exports/{_run(client, 'blind_export', vid, 'blind-e-1')}").json()
    assert performance["revealed"] and performance["revealed_through"] is None
    assert [p["retorno"] for p in performance["periods"]] == expected["retorno"].tolist()
    assert performance["cumulative"] == expected["capital"].iloc[-1] - 1
    assert performance["cumulative_spy"] == expected["capital_spy"].iloc[-1] - 1
    experiment = rl.get_experiment(exported["experiment_id"])
    assert (experiment["stage"], experiment["family"], experiment["n_periods"]) == (
        "LIVE_FORWARD", f"blind_validation_{vid}", 2)


def test_locked_validation_reveals_nothing_and_cannot_be_exported(monkeypatch):
    dates = _prices()
    _fake_ranking(monkeypatch, {"A": 90, "B": 80})
    vid = bv.create_validation("Test", WEIGHTS, 2, 1, dates[0].date().isoformat(), "2099-01-01")
    bv.record_rebalance(vid, as_of=dates[2].date().isoformat())
    with TestClient(create_app(Settings(config.DATA_DIR), today=lambda: TODAY)) as client:
        performance = client.get(f"/api/v1/research/blind-performance/"
                                 f"{_run(client, 'blind_performance', vid, 'blind-p-2')}")
        export = client.get(f"/api/v1/jobs/{_run(client, 'blind_export', vid, 'blind-e-2')}").json()
    assert performance.json()["revealed"] is False and performance.json()["periods"] == []
    assert "retorno" not in performance.text
    assert export["status"] == "failed"
    assert rl.list_experiments().empty


def test_preregistered_performance_stops_at_the_last_review_reached(monkeypatch):
    dates = _prices()
    _fake_ranking(monkeypatch, {"A": 90, "B": 80})
    vid = bv.create_validation("Test", WEIGHTS, 2, 1, dates[0].date().isoformat(), dates[4].date().isoformat())
    for day in (dates[1], dates[3], dates[8]):
        bv.record_rebalance(vid, as_of=day.date().isoformat())
    review = dates[5].date().isoformat()

    class Queries:
        def item(self, validation_id):
            return {"revealed": True, "revealed_through": review}

    cut = run_performance(Queries(), vid, lambda v, through: bv.get_status(v, reveal=True, as_of=through))
    assert [p["rebalance_date"] for p in cut["periods"]] == [dates[1].date().isoformat(), dates[3].date().isoformat()]
    entry = {"A": 103.0, "B": 53.0}  # Prices of the second rebalance (dates[3]).
    assert cut["periods"][-1]["retorno"] == bv._mark_to_market_return(["A", "B"], entry, pd.Timestamp(review))
    assert cut["periods"][-1]["retorno"] != bv._mark_to_market_return(["A", "B"], entry, pd.Timestamp(TODAY))


def test_blind_jobs_require_research_mode():
    vid = bv.create_validation("Test", WEIGHTS, 2, 3, "2026-01-01", "2099-01-01")
    (config.DATA_DIR / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        for kind in ("blind_rebalance", "blind_performance", "blind_export"):
            assert client.post("/api/v1/jobs", json={"kind": kind, "idempotency_key": f"{kind}-x1",
                                                     "blind": {"validation_id": vid}}).status_code == 403
