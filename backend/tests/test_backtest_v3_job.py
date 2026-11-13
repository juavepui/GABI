"""The V2/V3 comparison job (#249): V2's options, observed period only, Research mode and bounded artifact."""

import json
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError
from gabi.application.research import backtest_v3_comparison as comparison
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app

V2 = {"months": 3, "top_n": 20, "mode": "fast_dev", "max_symbols": 50, "initial_capital": 100_000,
      "commission_usd": 1, "spread_bps": 10, "rotation_hurdle_points": 0}
KIND = "backtest_v3_comparison"


def fake(start, end, options):
    return {"rebalances": 2, "sessions": 120, "v2": {"strict": True}, "v3": {},
            "data": {"missing": [f"S{i}" for i in range(comparison.MAX_ROWS + 5)], "anomalies": [], "exits": [],
                     "strict": True, "bases": {}},
            "policy_248": {"allocation_notes": [], "accounts": {}}}


@pytest.mark.parametrize(("start", "end", "options", "code"), [
    ("2024-01-02", "2025-07-03", V2, "reserved_period"),
    ("2009-06-01", "2010-06-01", V2, "reserved_period"),
    ("2019-01-02", "2020-01-02", {"months": 3, "top_n": 10, "cost_bps": 10, "universe_size": 50,
                                  "rotation_hurdle_points": 0}, "invalid_job"),
    ("2019-01-02", "2020-01-02", V2 | {"mode": "validation"}, "invalid_job"),
])
def test_the_command_takes_v2_options_within_the_observed_period(start, end, options, code):
    with pytest.raises(QueryError) as error:
        JobCommand(KIND, start=start, end=end, backtest_options=options)
    assert error.value.code == code
    validation = {key: value for key, value in V2.items() if key != "max_symbols"} | {"mode": "validation"}
    command = JobCommand(KIND, start="2019-01-02", end="2020-01-02", backtest_options=validation)
    assert command.backtest_options["max_symbols"] is None


def test_build_checks_the_period_itself_and_bounds_the_artifact():
    with pytest.raises(QueryError) as error:
        comparison.build("2016-01-01", "2026-01-01", V2, lambda *args: pytest.fail("ran over reserved data"))
    assert error.value.code == "reserved_period"
    artifact = comparison.build("2019-01-02", "2020-01-02", V2, fake)
    assert artifact["status"] == "ENGINE_DIAGNOSTIC" and artifact["independent_advantage_demonstrated"] is False
    assert len(artifact["data"]["missing"]) == comparison.MAX_ROWS and artifact["truncated"] == ["data.missing"]


def test_the_job_runs_in_research_mode_and_its_result_rechecks_the_period(tmp_path):
    request = {"kind": KIND, "idempotency_key": "v3-comparison-01", "start": "2019-01-02", "end": "2020-01-02",
               "backtest_options": V2}
    with TestClient(create_app(Settings(tmp_path))) as api:
        assert api.post("/api/v1/jobs", json=request).json()["error"]["code"] == "research_required"
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    with TestClient(create_app(Settings(tmp_path))) as api:
        created = api.post("/api/v1/jobs", json=request)
        assert created.status_code == 202, created.text
        job_id = created.json()["id"]
        assert Worker(SqliteJobs(tmp_path), lambda command: comparison.build(
            command.start, command.end, command.backtest_options, fake), tmp_path).run_once()
        result = api.get(f"/api/v1/jobs/{job_id}/result")
        assert result.status_code == 200, result.text
        assert result.json()["kind"] == KIND and result.json()["options"]["max_symbols"] == 50
    with closing(sqlite3.connect(SqliteJobs(tmp_path).path)) as db:
        params = SqliteJobs(tmp_path).get(job_id)["parameters"] | {"end": "2025-12-31"}
        db.execute("UPDATE jobs SET parameters=? WHERE id=?", (json.dumps(params), job_id))
        db.commit()
    with TestClient(create_app(Settings(tmp_path))) as api:
        assert api.get(f"/api/v1/jobs/{job_id}/result").json()["error"]["code"] == "reserved_period"
    (tmp_path / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with TestClient(create_app(Settings(tmp_path))) as api:
        assert api.get(f"/api/v1/jobs/{job_id}/result").status_code == 403
