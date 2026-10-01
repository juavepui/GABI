"""PBO/CSCV and block bootstrap jobs reproduce the Streamlit Research Lab calculations."""

import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from retired_block_bootstrap_ui import comparison_table, fraction_table

from gabi import block_bootstrap, config, stats_rigor
from gabi import research_lab as rl
from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError
from gabi.application.research import block_bootstrap_view as view
from gabi.application.research.experiment_analysis import build_bootstrap, build_pbo, distribution_frame
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.experiments import LegacyExperimentMath
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.experiments import SqliteExperiments
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(rl, "_current_git_commit", lambda: "abc1234")
    rng = np.random.default_rng(11)
    index = pd.date_range("2010-03-31", periods=40, freq="QE")
    ids = {}
    for name, drift in (("a", 0.02), ("b", 0.015), ("c", 0.01)):
        ids[name] = rl.log_experiment(f"M-{name}", "RESEARCH", False, family="mf", sharpe=drift * 10,
                                      periods_per_year=4.0, n_periods=40, data_fingerprint=f"fp-{name}",
                                      returns=pd.Series(rng.normal(drift, 0.05, 40), index=index))
    ids["short"] = rl.log_experiment("M-short", "RESEARCH", False, periods_per_year=4.0,
                                     returns=pd.Series(rng.normal(0.01, 0.05, 10), index=index[:10]))
    ids["shifted"] = rl.log_experiment("M-shifted", "RESEARCH", False, periods_per_year=4.0,
                                       returns=pd.Series(rng.normal(0.01, 0.05, 40), index=index + pd.Timedelta(days=1)))
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    return tmp_path, ids


def test_pbo_matches_legacy_page(lab):
    root, ids = lab
    picked = [ids["a"], ids["b"], ids["c"]]
    series = {}
    for experiment_id in picked:  # app/pages/11_Research_Lab.py before its retirement
        exp = rl.get_experiment(experiment_id)
        series[f"#{experiment_id} · {exp['model_id']} · Sharpe {exp['sharpe']:.2f}"] = exp["returns"]
    matrix = pd.concat(series, axis=1).dropna()
    legacy = stats_rigor.pbo_cscv(matrix, n_splits=min(16, (len(matrix) // 10) * 2 or 2))
    before = (root / "gabi.db").read_bytes()
    result = build_pbo(SqliteExperiments(root), {"experiment_ids": picked}, LegacyExperimentMath())
    assert (result["pbo"], result["n_combinations"], result["logits"]) == (
        legacy["pbo"], legacy["n_combinations"], legacy["logits"])
    assert result["n_splits"] == 8 and result["n_common_dates"] == 40
    assert [item["data_fingerprint"] for item in result["experiments"]] == ["fp-a", "fp-b", "fp-c"]
    assert (root / "gabi.db").read_bytes() == before


def test_pbo_reports_too_few_common_dates_without_computing(lab):
    root, ids = lab
    result = build_pbo(SqliteExperiments(root), {"experiment_ids": [ids["a"], ids["short"]]}, LegacyExperimentMath())
    assert result["pbo"] is None and result["n_common_dates"] == 10
    assert result["message"].startswith("Muy pocas fechas comunes")


def test_bootstrap_matches_legacy_button_and_view(lab):
    root, ids = lab
    strategy, benchmark = rl.get_experiment(ids["a"]), rl.get_experiment(ids["b"])
    matrix = strategy["returns"].to_frame("strategy")
    matrix["benchmark"] = benchmark["returns"]
    audit, distribution = block_bootstrap.analyze_sensitivity(matrix, periods_per_year=4.0, strategy="strategy")
    result = build_bootstrap(SqliteExperiments(root), {"experiment_id": ids["a"], "benchmark_id": ids["b"]},
                             LegacyExperimentMath())
    # The worker saves artifacts with sorted keys; the replicate columns must keep their order.
    saved = json.loads(json.dumps(result, allow_nan=False, default=str, sort_keys=True))
    assert saved["audit"]["experiments"]["benchmark"]["id"] == ids["b"]
    del saved["audit"]["experiments"]
    assert saved["audit"] == json.loads(json.dumps(audit, allow_nan=False, default=str))
    rebuilt = distribution_frame(saved["distribution"])
    pd.testing.assert_frame_equal(rebuilt, distribution, check_dtype=False)
    assert rebuilt.to_csv(index=False) == distribution.to_csv(index=False)
    reloaded = view.present(saved["audit"], rebuilt, saved["block_order"])
    assert [row["block_size"] for row in reloaded["intervals"]] == [
        row["block_size"] for row in view.present(audit, distribution)["intervals"]]
    assert saved["block_order"] == ["4", "2", "8"]

    shown = view.present(audit, distribution)
    pd.testing.assert_frame_equal(
        pd.DataFrame(shown["intervals"]).drop(columns=["series_label", "metric_label"]),
        block_bootstrap.interval_table(audit), check_dtype=False)
    legacy_comparison = comparison_table(audit)
    assert [row["mean"] for row in shown["comparisons"]] == legacy_comparison["Media"].tolist()
    assert [row["hac_upper"] for row in shown["comparisons"]] == legacy_comparison["HAC superior"].tolist()
    primary = audit["runs"][str(audit["primary_block"])]
    legacy_fractions = fraction_table(primary)
    assert [row["condition"] for row in shown["fractions"]] == legacy_fractions["Condición"].tolist()
    assert [row["fraction"] for row in shown["fractions"]] == legacy_fractions["Fracción bootstrap"].tolist()
    histogram = next(item for item in shown["histograms"] if item["column"] == "vs_benchmark/excess_mean")
    assert histogram["observed"] == primary["comparisons"]["benchmark"]["metrics"]["excess_mean"]["observed"]
    assert sum(item["fraction"] for item in histogram["bins"]) == pytest.approx(1)


def test_histograms_survive_a_range_below_float_resolution():
    audit = {"primary_block": 4, "runs": {"4": {"ci": .95, "series": {}, "means": {}, "comparisons": {}}}}
    values = 0.1 + np.arange(8) * 1e-17
    distribution = pd.DataFrame({"block_size": 4, "replicate": range(8), "x": values})
    histogram = view.histograms(audit, distribution)[0]
    assert histogram["valid_draws"] == 8 and sum(item["fraction"] for item in histogram["bins"]) == 1


@pytest.mark.parametrize(("name", "benchmark", "message"), [
    ("short", None, "menos de 30 observaciones"),
    ("a", "shifted", "no está alineado"),
])
def test_bootstrap_keeps_legacy_refusals(lab, name, benchmark, message):
    root, ids = lab
    result = build_bootstrap(SqliteExperiments(root), {"experiment_id": ids[name],
                                                       "benchmark_id": ids.get(benchmark)}, LegacyExperimentMath())
    assert result["audit"] is None and message in result["message"]


def test_commands_validate_options():
    with pytest.raises(QueryError):
        JobCommand("experiment_pbo", experiment_analysis={"experiment_ids": [1]})
    with pytest.raises(QueryError):
        JobCommand("experiment_bootstrap", experiment_analysis={"experiment_id": 1, "benchmark_id": 1})
    with pytest.raises(QueryError):
        JobCommand("backtest_register", experiment_analysis={"experiment_ids": [1, 2]})
    command = JobCommand("experiment_pbo", experiment_analysis={"experiment_ids": [3, 1]})
    assert command.experiment_analysis == {"experiment_ids": [1, 3]}


def test_jobs_run_in_worker_and_previews_require_research(lab):
    root, ids = lab
    app = create_app(Settings(root))
    with TestClient(app) as client:
        pbo = client.post("/api/v1/jobs", json={"kind": "experiment_pbo", "idempotency_key": "pbo-test-1",
                                                 "experiment_analysis": {"experiment_ids": [ids["a"], ids["b"]]}})
        boot = client.post("/api/v1/jobs", json={"kind": "experiment_bootstrap", "idempotency_key": "boot-test-1",
                                                  "experiment_analysis": {"experiment_id": ids["a"]}})
        assert pbo.status_code == boot.status_code == 202
        worker = Worker(SqliteJobs(root), LegacyExecutor(Settings(root)), root)
        assert worker.run_once() and worker.run_once()
        pbo_view = client.get(f"/api/v1/research/experiment-pbo/{pbo.json()['id']}")
        boot_view = client.get(f"/api/v1/research/experiment-bootstrap/{boot.json()['id']}")
        csv = client.get(f"/api/v1/research/experiment-bootstrap/{boot.json()['id']}/distributions.csv")
        assert pbo_view.status_code == boot_view.status_code == csv.status_code == 200
        assert pbo_view.json()["n_splits"] == 8 and 0 <= pbo_view.json()["pbo"] <= 1
        body = boot_view.json()
        assert body["view"]["primary_block"] == 4 and body["view"]["n_boot"] == 4096
        assert csv.text.splitlines()[0] == ("block_size,replicate,strategy/cagr,strategy/volatility,"
                                            "strategy/sharpe,strategy/max_drawdown,strategy/es5")
        assert len(csv.text.splitlines()) == 1 + 3 * 4096
        (root / "app_mode.json").write_text('{"mode":"INVESTOR"}')
        assert client.get(f"/api/v1/research/experiment-pbo/{pbo.json()['id']}").status_code == 403
        assert client.post("/api/v1/jobs", json={
            "kind": "experiment_pbo", "idempotency_key": "pbo-test-2",
            "experiment_analysis": {"experiment_ids": [ids["a"], ids["c"]]}}).status_code == 403
