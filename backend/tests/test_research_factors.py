"""Factor jobs are explicit, bounded, and cannot read reserved future returns."""

import json
import sqlite3
from contextlib import closing

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError
from gabi.application.research.factors import build_factor_analysis, quantile_means
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.factor_prices import SqliteFactorPrices
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


def _request(api, **extra):
    return api.post("/api/v1/jobs", json={
        "kind": "factor_analysis", "idempotency_key": "factor-test-01",
        "start": "2019-01-02", "end": "2024-01-02", "factor_months": 3,
        "factor_mode": "fast_dev", "factor_max_symbols": 50, **extra,
    })


@pytest.mark.parametrize(("start", "end", "expected"), [
    ("2009-01-01", "2010-01-01", "reserved_period"),
    ("2019-01-01", "2025-01-01", "reserved_period"),
    ("2024-01-01", "2024-01-01", "invalid_job"),
    ("2010-01-01", "2024-01-01", "invalid_job"),
])
def test_factor_job_rejects_reserved_or_unbounded_windows(tmp_path, start, end, expected):
    with TestClient(create_app(Settings(tmp_path))) as api:
        response = _request(api, start=start, end=end)
    assert response.status_code in (403, 422)
    assert response.json()["error"]["code"] == expected
    assert not (tmp_path / "gabi_jobs.db").exists()


def test_factor_job_rejects_incomplete_or_inconsistent_options(tmp_path):
    with pytest.raises(QueryError):
        JobCommand("factor_analysis", start="2019-01-01", end=None, factor_months=3,
                   factor_mode="validation")
    with pytest.raises(QueryError):
        JobCommand("factor_analysis", start="2019-01-01", end="2020-01-01", factor_months=3,
                   factor_mode="validation", factor_max_symbols=50)
    with pytest.raises(QueryError):
        JobCommand("quality", factor_months=3)
    with pytest.raises(QueryError, match="Solo se permite"):
        SqliteFactorPrices(tmp_path)(["SECRET"], "2025-07-03", "2026-07-03")


def test_factor_job_publishes_original_metrics_with_hash_and_no_reserved_read(tmp_path):
    calls = []
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')

    def run(start, end, *, months, mode, max_symbols):
        calls.append((start, end, months, mode, max_symbols))
        return {
            "summary": pd.DataFrame([{"factor": "value_score", "horizonte": 3,
                                      "sector_neutral": False, "ic_mean": 0.12, "ic_std": float("nan"),
                                      "icir": float("nan"), "pct_ic_positive": 0.7,
                                      "q_spread": 0.03, "n_periods": 8}]),
            "ic_series": pd.DataFrame([{"fecha": "2019-01-02", "factor": "value_score",
                                        "horizonte": 3, "ic_raw": 0.12}]),
            "quantile_returns": pd.DataFrame([{"factor": "value_score", "horizonte": 3,
                                               "quantil": 5, "retorno_medio": 0.04}]),
            "turnover": pd.DataFrame([{"factor": "value_score", "quantil": 5,
                                      "turnover": 0.2}]),
            "skipped": [{"fecha": "2019-04-02", "motivo": "sin cobertura"}],
        }

    with TestClient(create_app(Settings(tmp_path))) as api:
        created = _request(api)
        assert created.status_code == 202, created.text
        job_id = created.json()["id"]
        assert Worker(SqliteJobs(tmp_path), lambda command: build_factor_analysis(
            command.start, command.end, command.factor_months, command.factor_mode,
            command.factor_max_symbols, run), tmp_path).run_once()
        assert calls == [("2019-01-02", "2024-01-02", 3, "fast_dev", 50)]
        preview = api.get(f"/api/v1/research/factors/{job_id}")
        assert preview.status_code == 200, preview.text
        result = preview.json()
        assert result["summary"][0]["ic_mean"] == 0.12
        assert result["summary"][0]["ic_std"] is None
        assert result["status"] == "RETROSPECTIVE_EXPLORATORY"
        assert result["independent_advantage_demonstrated"] is False
        assert result["skipped_count"] == 1
        assert result["skipped"] == [{"fecha": "2019-04-02", "motivo": "sin cobertura"}]
        assert result["quantile_means"] == [{"factor": "value_score", "horizonte": 3, "quantil": 5,
                                             "retorno_medio": 0.04, "retorno_medio_neutral": None}]
        full = api.get(f"/api/v1/jobs/{job_id}/result").json()
        assert full["ic_series"][0]["ic_raw"] == 0.12
        assert full["quantile_returns"][0]["retorno_medio"] == 0.04
        assert full["summary"][0]["ic_std"] is None
        assert result["result_sha256"] == SqliteJobs(tmp_path).get(job_id)["result_sha256"]


def test_factor_result_read_rechecks_reserved_dates(tmp_path):
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    store = SqliteJobs(tmp_path)
    command = JobCommand("factor_analysis", start="2019-01-01", end="2020-01-01",
                         factor_months=3, factor_mode="validation")
    job = store.enqueue(command, "factor-old-job", "ui")
    with closing(sqlite3.connect(store.path)) as db:
        params = job["parameters"] | {"end": "2025-01-01"}
        db.execute("UPDATE jobs SET parameters=? WHERE id=?", (json.dumps(params), job["id"]))
        db.commit()
    with TestClient(create_app(Settings(tmp_path))) as api:
        response = api.get(f"/api/v1/jobs/{job['id']}/result")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "reserved_period"
        assert api.get(f"/api/v1/research/factors/{job['id']}").status_code == 403


def test_factor_job_requires_research_mode_on_submit_and_result(tmp_path):
    with TestClient(create_app(Settings(tmp_path))) as api:
        response = _request(api)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "research_required"
    assert not (tmp_path / "gabi_jobs.db").exists()
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    with TestClient(create_app(Settings(tmp_path))) as api:
        job_id = _request(api).json()["id"]
    (tmp_path / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with TestClient(create_app(Settings(tmp_path))) as api:
        assert api.get(f"/api/v1/jobs/{job_id}/result").status_code == 403
        assert api.get(f"/api/v1/research/factors/{job_id}").status_code == 403


def test_quantile_means_match_streamlit_quintile_chart():
    rows = pd.DataFrame([
        {"fecha": f"2019-{month:02d}-02", "factor": factor, "horizonte": horizon, "quantil": quantile,
         "retorno_medio": 0.01 * quantile + 0.003 * month - 0.002 * horizon,
         "retorno_medio_neutral": float("nan") if month == 1 else 0.001 * quantile * month}
        for month in range(1, 5) for factor in ("value_score", "quality_score")
        for horizon in (1, 3) for quantile in range(1, 6)
    ])
    artifact = build_factor_analysis("2019-01-02", "2020-01-02", 3, "fast_dev", 50, lambda *_, **__: {
        "summary": pd.DataFrame(), "ic_series": pd.DataFrame(), "quantile_returns": rows,
        "turnover": pd.DataFrame(), "skipped": []})
    means = {(row["factor"], row["horizonte"], row["quantil"]): row
             for row in quantile_means(artifact["quantile_returns"])}
    assert len(means) == 2 * 2 * 5
    for (factor, horizon), _ in rows.groupby(["factor", "horizonte"]):
        q_view = rows[(rows["factor"] == factor) & (rows["horizonte"] == horizon)]
        for column in ("retorno_medio", "retorno_medio_neutral"):
            for quantile, value in q_view.groupby("quantil")[column].mean().items():
                assert means[(factor, horizon, quantile)][column] == value
    assert quantile_means([]) == []
