"""Portfolio Lab runs as a Research job with the engine's exact results and the observed-period reservation."""

import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_portfolio_lab import _seed_prices

from gabi import config, portfolio_metrics
from gabi import portfolio_lab as pl
from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app

OPTIONS = {"months": 3, "top_n": 2, "initial_capital": 10_000, "schemes": list(pl.SCHEMES),
           "mode": "fast_dev", "max_symbols": 50}


@pytest.fixture
def market(monkeypatch):
    dates = pd.date_range("2022-01-01", "2023-10-15", freq="D")
    _seed_prices(dates, [("AAA", list(100.0 + np.cumsum(np.random.default_rng(1).normal(0, .5, len(dates))))),
                         ("BBB", list(100.0 + np.cumsum(np.random.default_rng(2).normal(0, .5, len(dates))))),
                         ("SPY", list(100.0 + np.cumsum(np.random.default_rng(3).normal(0, .3, len(dates)))))])
    monkeypatch.setattr(pl.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})
    monkeypatch.setattr(pl.screener_asof, "build_ranking_as_of",
                        lambda day, symbols: {"table": pd.DataFrame(
                            {"composite_score": [80, 60], "score_coverage": [.9, .9], "sector": ["Tech", "Health"]},
                            index=["AAA", "BBB"])})
    (config.DATA_DIR / "app_mode.json").write_text('{"mode":"RESEARCH"}')


def _run_job(client, start, end, options, key):
    job = client.post("/api/v1/jobs", json={"kind": "portfolio_lab", "idempotency_key": key, "start": start,
                                             "end": end, "portfolio_options": options})
    assert job.status_code == 202, job.text
    worker = Worker(SqliteJobs(config.DATA_DIR), LegacyExecutor(Settings(config.DATA_DIR)), config.DATA_DIR)
    assert worker.run_once()
    return job.json()["id"]


def test_job_reproduces_the_streamlit_run_exactly(market):
    expected = pl.run_portfolio_lab("2023-01-02", "2023-07-02", months=3, top_n=2, initial_capital=10_000.0,
                                    max_symbols=50, mode="fast_dev", schemes=pl.SCHEMES)
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        job_id = _run_job(client, "2023-01-02", "2023-07-02", OPTIONS, "portfolio-lab-1")
        preview = client.get(f"/api/v1/research/portfolio-lab/{job_id}")
        artifact = client.get(f"/api/v1/jobs/{job_id}/result").json()
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert [scheme["id"] for scheme in body["schemes"]] == list(expected["schemes"])
    curve = pd.DataFrame(artifact["curve"]).set_index("fecha")
    for scheme in body["schemes"]:
        data = expected["schemes"][scheme["id"]]
        assert scheme["daily"] == pytest.approx(json.loads(json.dumps(data["daily"])))
        assert (scheme["hhi"], scheme["top3_contribution_to_risk"], scheme["tracking_error"]) == (
            data["hhi"], data["top3_contribution_to_risk"], data["tracking_error"])
        assert scheme["last_weights"] == data["last_weights"]
        assert scheme["contribution_to_risk"] == data["contribution_to_risk"]
        assert scheme["comision_total"] == data["comision_total"]
        assert curve[scheme["id"]].tolist() == data["nav_curve"].tolist()
        nav = data["nav_curve"]
        tail = next(row for row in body["tail"]["series"] if row["name"] == data["label"])["summary"]
        legacy = portfolio_metrics.tail_risk_metrics(portfolio_metrics.returns_from_nav(nav),
                                                     horizon="una sesión (NAV diario)")
        assert (tail["level_95"]["var"], tail["level_99"]["expected_shortfall"]) == (
            legacy["95"]["var"], legacy["99"]["expected_shortfall"])
    assert curve["spy"].tolist() == expected["nav_curve_spy"].tolist()
    shown = {scheme: {name: {key: value for key, value in outcome.items() if value is not None}
                      for name, outcome in rows.items()} for scheme, rows in body["scenarios"].items()}
    assert shown == json.loads(json.dumps(expected["scenarios"]))  # The contract adds the absent fields as null.
    assert body["skipped"] == expected["skipped"]
    assert body["labels"] == pl.SCHEME_LABELS and body["scenario_ground"] == pl.SCENARIO_GROUND


@pytest.mark.parametrize(("start", "end", "change", "status"), [
    ("2025-01-02", "2026-01-02", {}, 403),  # Prices after the observed cut are reserved.
    ("2009-01-02", "2010-06-01", {}, 403),
    ("2023-01-02", "2023-07-02", {"mode": "validation"}, 422),
    ("2023-01-02", "2023-07-02", {"schemes": []}, 422),
    ("2023-01-02", "2023-07-02", {"top_n": 1}, 422),
])
def test_invalid_or_reserved_runs_are_rejected(market, start, end, change, status):
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        response = client.post("/api/v1/jobs", json={"kind": "portfolio_lab", "idempotency_key": "portfolio-bad",
                                                      "start": start, "end": end,
                                                      "portfolio_options": OPTIONS | change})
    assert response.status_code == status


def test_scheme_order_is_canonical_and_research_mode_is_required(market):
    command = JobCommand("portfolio_lab", start="2023-01-02", end="2023-07-02",
                         portfolio_options=OPTIONS | {"schemes": ["risk_parity", "equal_weight"]})
    assert command.portfolio_options["schemes"] == ["equal_weight", "risk_parity"]
    with pytest.raises(QueryError):
        JobCommand("backtest_v2", start="2023-01-02", end="2023-07-02", portfolio_options=OPTIONS)
    (config.DATA_DIR / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with TestClient(create_app(Settings(config.DATA_DIR))) as client:
        assert client.post("/api/v1/jobs", json={"kind": "portfolio_lab", "idempotency_key": "portfolio-mode",
                                                 "start": "2023-01-02", "end": "2023-07-02",
                                                 "portfolio_options": OPTIONS}).status_code == 403
