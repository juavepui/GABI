"""V1/V2 backtests run only as explicit Research jobs over the observed window."""

import json
import sqlite3
from contextlib import closing

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gabi import multifactor_backtest, portfolio_backtest, portfolio_metrics
from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError
from gabi.application.research.backtests import build_backtest
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.backtests import run_backtest_v1, run_backtest_v2
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app

V1 = {"months": 3, "top_n": 10, "cost_bps": 10, "universe_size": 50, "rotation_hurdle_points": 0}
V2 = {"months": 3, "top_n": 20, "mode": "fast_dev", "max_symbols": 200, "initial_capital": 100_000,
      "commission_usd": 1, "spread_bps": 10, "rotation_hurdle_points": 0}


def _v1_result(*_args, **_kwargs):
    periods = pd.DataFrame([
        {"fecha": "2019-01-02", "hasta": "2019-04-02", "candidatas": "AAA, BBB",
         "cobertura universo": "40/50", "retorno": 0.05, "spy": 0.03, "universo_ew": 0.04,
         "turnover_pct": None},
        {"fecha": "2019-04-02", "hasta": "2019-07-02", "candidatas": "AAA, CCC",
         "cobertura universo": "41/50", "retorno": -0.02, "spy": 0.01, "universo_ew": 0.0,
         "turnover_pct": 50.0},
    ])
    periods["capital"] = (1 + periods["retorno"]).cumprod()
    periods["spy_capital"] = (1 + periods["spy"]).cumprod()
    periods["universo_capital"] = (1 + periods["universo_ew"]).cumprod()
    metrics = {"anualizado": 0.1, "vol_anualizada": 0.2, "sharpe": 0.3, "sortino": float("nan"),
               "max_drawdown": -0.02}
    return {"periods": periods, "skipped": [{"fecha": "2019-07-02", "motivo": "sin cobertura"}],
            "data_quality": {"2019-01-02": {"n": 50}}, "rotation_hurdle_points": 0.0,
            "turnover_medio": 50.0, "return": 0.029, "spy_return": 0.0403, "universo_ew_return": 0.04,
            "drawdown": -0.02, "metrics": {"estrategia": metrics, "universo_ew": metrics, "spy": metrics}}


def _nav(seed: int) -> pd.Series:
    days = pd.bdate_range("2019-01-03", periods=130)
    steps = np.random.default_rng(seed).normal(0.0004, 0.01, len(days))
    return pd.Series(100_000 * np.cumprod(1 + steps), index=days)


def _v2_engine(*_args, **_kwargs):
    return {"mode": "fast_dev", "skipped": [], "data_quality": {}, "rotation_hurdle_points": 0.0,
            "periods": pd.DataFrame([{"fecha": "2019-01-02", "hasta": "2019-04-02", "held": "",
                                      "sold": "", "bought": "AAA, BBB", "turnover_pct": 100.0,
                                      "comision_pagada": 2.0, "spread_pagado": 10.0,
                                      "coste_total": 12.0}]),
            "exit_events": [{"symbol": "OLD", "fecha": "2019-02-01", "estado": "merger", "estricto": True}],
            "strict_result": True, "nav_curve": _nav(1), "nav_curve_spy": _nav(2),
            "turnover_medio": 100.0, "comision_total": 2.0, "spread_total": 10.0, "coste_total": 12.0,
            "initial_capital": 100_000.0, "capital_final": float(_nav(1).iloc[-1])}


def _request(api, kind="backtest_v1", options=V1, **extra):
    return api.post("/api/v1/jobs", json={"kind": kind, "idempotency_key": "backtest-test-01",
                                          "start": "2019-01-02", "end": "2020-01-02",
                                          "backtest_options": options, **extra})


@pytest.mark.parametrize(("start", "end", "options", "code"), [
    ("2009-06-01", "2010-06-01", V1, "reserved_period"),
    ("2024-01-02", "2025-07-03", V1, "reserved_period"),
    ("2019-01-02", "2019-01-02", V1, "invalid_job"),
    ("2019-01-02", "2020-01-02", V1 | {"mode": "validation"}, "invalid_job"),
    ("2019-01-02", "2020-01-02", V1 | {"universe_size": 200}, "invalid_job"),
    ("2019-01-02", "2020-01-02", V1 | {"top_n": 2.5}, "invalid_job"),
])
def test_backtest_command_rejects_reserved_or_inconsistent_parameters(start, end, options, code):
    with pytest.raises(QueryError) as error:
        JobCommand("backtest_v1", start=start, end=end, backtest_options=options)
    assert error.value.code == code
    with pytest.raises(QueryError):
        JobCommand("backtest_v2", start="2019-01-02", end="2020-01-02",
                   backtest_options=V2 | {"mode": "validation"})
    with pytest.raises(QueryError):
        JobCommand("backtest_v2", start="2019-01-02", end="2020-01-02",
                   backtest_options=V2 | {"initial_capital": 1_000, "commission_usd": 1_000})
    with pytest.raises(QueryError):
        JobCommand("quality", backtest_options=V1)
    validation = {key: value for key, value in V2.items() if key != "max_symbols"} | {"mode": "validation"}
    command = JobCommand("backtest_v2", start="2019-01-02", end="2020-01-02", backtest_options=validation)
    assert command.backtest_options["max_symbols"] is None


def test_backtest_requires_research_mode_and_rejects_bad_api_options(tmp_path):
    with TestClient(create_app(Settings(tmp_path))) as api:
        denied = _request(api)
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "research_required"
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    with TestClient(create_app(Settings(tmp_path))) as api:
        assert _request(api, options=V1 | {"unknown": 1}).status_code == 422
        assert _request(api, kind="backtest_v2", options=V1).status_code == 422
    assert not (tmp_path / "gabi_jobs.db").exists()


def test_v1_job_publishes_complete_artifact_and_typed_preview(tmp_path):
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    calls = []

    def run(start, end, options):
        calls.append((start, end, options))
        return _v1_result()

    with TestClient(create_app(Settings(tmp_path))) as api:
        created = _request(api)
        assert created.status_code == 202, created.text
        job_id = created.json()["id"]
        assert created.json()["parameters"]["backtest_options"]["cost_bps"] == 10.0
        assert Worker(SqliteJobs(tmp_path), lambda command: build_backtest(
            command.kind, command.start, command.end, command.backtest_options, run), tmp_path).run_once()
        assert calls == [("2019-01-02", "2020-01-02", V1 | {"cost_bps": 10.0, "top_n": 10,
                                                            "rotation_hurdle_points": 0.0})]
        preview = api.get(f"/api/v1/research/backtests/{job_id}")
        assert preview.status_code == 200, preview.text
        data = preview.json()
        assert data["kind"] == "backtest_v1"
        assert data["independent_advantage_demonstrated"] is False
        assert [row["name"] for row in data["series"]] == ["estrategia", "universo_ew", "spy"]
        assert data["series"][0]["total_return"] == 0.029
        assert data["series"][0]["sortino"] is None
        assert data["periods"][0]["cobertura_universo"] == "40/50"
        assert data["curve"][-1] == {"fecha": "2019-07-02", "estrategia": pytest.approx(1.029),
                                     "universo_ew": pytest.approx(1.04), "spy": pytest.approx(1.0403)}
        assert data["skipped"] == [{"fecha": "2019-07-02", "motivo": "sin cobertura"}]
        full = api.get(f"/api/v1/jobs/{job_id}/result").json()
        assert full["data_quality"] == {"2019-01-02": {"n": 50}}
        assert full["periods"][1]["capital"] == pytest.approx(1.029)
        assert data["result_sha256"] == SqliteJobs(tmp_path).get(job_id)["result_sha256"]
        assert api.get(f"/api/v1/research/factors/{job_id}").status_code == 404
    (tmp_path / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with TestClient(create_app(Settings(tmp_path))) as api:
        assert api.get(f"/api/v1/research/backtests/{job_id}").status_code == 403


def test_backtest_result_rechecks_reserved_dates_of_persisted_jobs(tmp_path):
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    store = SqliteJobs(tmp_path)
    job = store.enqueue(JobCommand("backtest_v1", start="2019-01-02", end="2020-01-02",
                                   backtest_options=V1), "backtest-old-job", "ui")
    with closing(sqlite3.connect(store.path)) as db:
        params = job["parameters"] | {"end": "2025-12-31"}
        db.execute("UPDATE jobs SET parameters=? WHERE id=?", (json.dumps(params), job["id"]))
        db.commit()
    with TestClient(create_app(Settings(tmp_path))) as api:
        response = api.get(f"/api/v1/research/backtests/{job['id']}")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "reserved_period"


def test_legacy_adapters_pass_parameters_and_match_streamlit_metrics(monkeypatch):
    seen = {}
    monkeypatch.setattr(multifactor_backtest, "run", lambda *args, **kwargs: seen.update(
        v1=(args, kwargs)) or _v1_result())
    monkeypatch.setattr(portfolio_backtest, "run", lambda *args, **kwargs: seen.update(
        v2=(args, kwargs)) or _v2_engine())
    run_backtest_v1("2019-01-02", "2020-01-02", V1 | {"rotation_hurdle_points": 2.0})
    assert seen["v1"] == (("2019-01-02", "2020-01-02", 3, 10, 10),
                          {"max_symbols": 50, "rotation_hurdle_points": 2.0})
    result = run_backtest_v2("2019-01-02", "2020-01-02", V2)
    assert seen["v2"][1] == {"months": 3, "top_n": 20, "max_symbols": 200, "mode": "fast_dev",
                             "initial_capital": 100_000, "commission_usd": 1, "spread_bps": 10,
                             "rotation_hurdle_points": 0}

    nav, nav_spy = _nav(1), _nav(2)
    returns, returns_spy = nav.pct_change().dropna(), nav_spy.pct_change().dropna()
    daily = multifactor_backtest.daily_risk_metrics(nav)
    assert result["metrics"] == {
        "estrategia": daily, "spy": multifactor_backtest.daily_risk_metrics(nav_spy),
        "calmar": portfolio_metrics.calmar_ratio(daily["anualizado"], daily["max_drawdown"]),
        "recovery_days": portfolio_metrics.recovery_time(nav),
        "beta": portfolio_metrics.beta_vs_benchmark(returns, returns_spy),
        "information_ratio": portfolio_metrics.information_ratio(returns, returns_spy),
        "capture": portfolio_metrics.capture_ratios(returns, returns_spy),
    }
    artifact = build_backtest("backtest_v2", "2019-01-02", "2020-01-02", V2, lambda *_: result)
    assert len(artifact["curve"]) == len(nav)
    assert artifact["curve"][0] == {"fecha": "2019-01-03", "estrategia": float(nav.iloc[0]),
                                    "spy": float(nav_spy.iloc[0])}
    assert artifact["exit_events"][0]["symbol"] == "OLD"


def _streamlit_v1_kwargs(test, universe_size, n_picks, interval, bt_cost, start, end, family, notes):
    """The keyword arguments app/pages/8_Ranking_Historico.py passed for V1."""
    strat_m = test["metrics"]["estrategia"]
    return dict(
        universe=f"S&P 500 histórico, muestra de {universe_size}",
        factors="Value/Quality/Momentum/Risk", n_positions=int(n_picks),
        rebalance={1: "Monthly", 3: "Quarterly", 6: "Semiannual", 12: "Annual"}[interval],
        cost_model=f"V1: {bt_cost:.0f}pb round-trip sobre el 100% de cada posición cada periodo",
        is_start=start, is_end=end, family=family or None,
        sharpe=strat_m["sharpe"], sortino=strat_m["sortino"], max_drawdown=strat_m["max_drawdown"],
        total_return=test["return"], n_periods=len(test["periods"]), periods_per_year=12 / interval,
        returns=test["periods"].set_index(pd.to_datetime(test["periods"]["hasta"]))["retorno"],
        notes=notes or None, result={"data_quality": test.get("data_quality", {})})


def _roundtrip(artifact):
    return json.loads(json.dumps(artifact, allow_nan=False, default=str, sort_keys=True))


def test_registration_matches_streamlit_experiment_fields():
    from gabi import research_lab
    from gabi.application.research.backtests import STAGES, experiment_from_backtest, normalize_registration

    assert list(STAGES) == research_lab.STAGES
    registration = normalize_registration({"source_job_id": "a" * 32, "stage": "RESEARCH",
                                           "hypothesis_registered": False, "family": " v1 ", "notes": ""})
    assert registration["family"] == "v1" and registration["notes"] is None
    test = _v1_result()
    artifact = _roundtrip(build_backtest("backtest_v1", "2019-01-02", "2020-01-02", V1, lambda *_: test))
    record = experiment_from_backtest(artifact, registration, "f" * 64)
    expected = _streamlit_v1_kwargs(test, 50, 10, 3, 10.0, "2019-01-02", "2020-01-02", "v1", "")
    returns, expected_returns = record.pop("returns"), expected.pop("returns")
    pd.testing.assert_series_equal(returns, expected_returns, check_names=False)
    assert {str(k): float(v) for k, v in returns.items()} == {
        str(k): float(v) for k, v in expected_returns.items()}
    assert record.pop("result") == expected.pop("result") | {
        "backtest_job_id": "a" * 32, "backtest_result_sha256": "f" * 64,
        "data_fingerprint_scope": "registration"}
    assert record.pop("model_id") == "GABI-MF-v1"
    assert (record.pop("stage"), record.pop("hypothesis_registered")) == ("RESEARCH", False)
    # SQLite stores NaN as NULL, so a NaN metric from the engine and None from JSON log the same row.
    assert record == {key: None if isinstance(value, float) and value != value else value
                      for key, value in expected.items()}

    engine = _v2_engine()
    nav = engine["nav_curve"]
    engine["metrics"] = {"estrategia": multifactor_backtest.daily_risk_metrics(nav),
                         "spy": multifactor_backtest.daily_risk_metrics(engine["nav_curve_spy"]),
                         "calmar": None, "recovery_days": None, "beta": None, "information_ratio": None,
                         "capture": {"upside": None, "downside": None}}
    artifact = _roundtrip(build_backtest("backtest_v2", "2019-01-02", "2020-01-02", V2, lambda *_: engine))
    record = experiment_from_backtest(artifact, registration | {"stage": "IN_SAMPLE"}, "f" * 64)
    pd.testing.assert_series_equal(record["returns"], nav.pct_change().dropna(), check_names=False,
                                   check_freq=False)
    assert record["total_return"] == float(nav.iloc[-1] / nav.iloc[0] - 1)
    assert record["universe"] == "S&P 500 histórico, muestra de 200"
    assert record["cost_model"] == "V2: 1.00$ fijo + 10pb spread, solo sobre variación de peso real"
    assert (record["n_periods"], record["periods_per_year"]) == (len(nav) - 1, 252)
    assert record["result"]["capital_inicial"] == 100_000.0


def test_register_job_logs_once_with_fingerprint_and_provenance(tmp_path, monkeypatch):
    from gabi import config, data_quality, research_lab
    from gabi.infrastructure.legacy.jobs import LegacyExecutor

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(data_quality, "compute_data_fingerprint", lambda *a, **k: "fp-test")
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    store = SqliteJobs(tmp_path)
    source = store.enqueue(JobCommand("backtest_v1", start="2019-01-02", end="2020-01-02",
                                      backtest_options=V1), "backtest-source-1", "ui")
    assert Worker(store, lambda command: build_backtest(command.kind, command.start, command.end,
                                                        command.backtest_options, _v1_result), tmp_path).run_once()
    executor = LegacyExecutor(Settings(tmp_path))
    request = {"kind": "backtest_register", "idempotency_key": "register-test-01",
               "research_log": {"source_job_id": source["id"], "stage": "RESEARCH",
                                "hypothesis_registered": True, "family": "mf-v1", "notes": "nota"}}
    with TestClient(create_app(Settings(tmp_path))) as api:
        created = api.post("/api/v1/jobs", json=request)
        assert created.status_code == 202, created.text
        assert Worker(store, executor, tmp_path).run_once()
        result = api.get(f"/api/v1/jobs/{created.json()['id']}/result").json()
        assert result["data_fingerprint"] == "fp-test"
        experiments = research_lab.list_experiments()
        assert len(experiments) == 1
        row = experiments.iloc[0]
        assert row["id"] == result["experiment_id"]
        assert (row["model_id"], row["stage"], row["family"], row["hypothesis_registered"]) == (
            "GABI-MF-v1", "RESEARCH", "mf-v1", 1)
        assert row["data_fingerprint"] == "fp-test"
        assert json.loads(row["returns_json"]) == {"2019-04-02 00:00:00": 0.05, "2019-07-02 00:00:00": -0.02}
        stored = json.loads(row["result_json"])
        assert stored["backtest_job_id"] == source["id"]
        assert stored["backtest_result_sha256"] == store.get(source["id"])["result_sha256"]

        again = api.post("/api/v1/jobs", json=request | {"idempotency_key": "register-test-02"})
        assert Worker(store, executor, tmp_path).run_once()
        assert store.get(again.json()["id"])["status"] == "failed"
        assert len(research_lab.list_experiments()) == 1

        bad = api.post("/api/v1/jobs", json=request | {"idempotency_key": "register-test-03",
                                                       "research_log": request["research_log"] | {"stage": "X"}})
        assert bad.status_code == 422
    (tmp_path / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with TestClient(create_app(Settings(tmp_path))) as api:
        denied = api.post("/api/v1/jobs", json=request | {"idempotency_key": "register-test-04"})
        assert denied.status_code == 403
