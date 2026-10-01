"""PSR/DSR and tail risk of logged experiments match the Streamlit Research Lab calls."""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gabi import config, portfolio_metrics, stats_rigor
from gabi import research_lab as rl
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(rl, "_current_git_commit", lambda: "abc1234")
    rng = np.random.default_rng(7)
    index = pd.date_range("2011-03-31", periods=40, freq="QE")
    ids = {
        "with_returns": rl.log_experiment("A", "RESEARCH", False, family="mf", sharpe=0.8, n_periods=40,
                                          periods_per_year=4.0,
                                          returns=pd.Series(rng.normal(0.02, 0.06, 40), index=index)),
        "summary_only": rl.log_experiment("B", "RESEARCH", False, family="mf", sharpe=0.3),
        "other_family": rl.log_experiment("C", "RESEARCH", False, family="other", sharpe=1.1),
        "no_sharpe": rl.log_experiment("D", "RESEARCH", False, family="mf"),
    }
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    return tmp_path, ids


def _legacy_dsr(experiment_id, family):
    """The expressions of app/pages/11_Research_Lab.py before its retirement."""
    experiments = rl.list_experiments()
    with_sharpe = experiments[experiments["sharpe"].notna()]
    family_rows = with_sharpe[with_sharpe["family"] == family] if family else with_sharpe
    selected = rl.get_experiment(experiment_id)
    if selected["returns"] is not None:
        exact = stats_rigor.probabilistic_sharpe_ratio_from_returns(selected["returns"],
                                                                    selected["periods_per_year"] or 4)
        skew, kurtosis = exact["skew"], exact["kurtosis"]
    else:
        skew, kurtosis = 0.0, 3.0
    result = stats_rigor.deflated_sharpe_ratio(
        selected["sharpe"], family_rows["sharpe"].tolist(), n_obs=int(selected["n_periods"] or 36),
        periods_per_year=float(selected["periods_per_year"] or 4), skew=skew, kurtosis=kurtosis)
    raw = stats_rigor.probabilistic_sharpe_ratio_annualized(
        selected["sharpe"], int(selected["n_periods"] or 36), float(selected["periods_per_year"] or 4),
        skew=skew, kurtosis=kurtosis, benchmark_sharpe=0.0)
    return raw, result


@pytest.mark.parametrize("name", ["with_returns", "summary_only"])
def test_deflated_sharpe_matches_legacy_page(lab, name):
    root, ids = lab
    before = (root / "gabi.db").read_bytes()
    raw, legacy = _legacy_dsr(ids[name], "mf")
    with TestClient(create_app(Settings(root))) as client:
        response = client.get("/api/v1/research/experiment-statistics/deflated-sharpe",
                              params={"experiment_id": ids[name], "family": "mf"})
    assert response.status_code == 200
    body = response.json()
    assert body["psr"] == raw
    assert (body["dsr"], body["sr0_benchmark"], body["n_trials"]) == (
        legacy["dsr"], legacy["sr0_benchmark"], legacy["n_trials"])
    assert body["n_trials"] == 2 and sorted(body["trial_ids"]) == sorted([ids["with_returns"], ids["summary_only"]])
    assert body["moments"] == ("returns" if name == "with_returns" else "normal_approximation")
    assert (root / "gabi.db").read_bytes() == before


def test_deflated_sharpe_rejects_small_families_and_foreign_experiments(lab):
    root, ids = lab
    with TestClient(create_app(Settings(root))) as client:
        small = client.get("/api/v1/research/experiment-statistics/deflated-sharpe",
                           params={"experiment_id": ids["other_family"], "family": "other"})
        foreign = client.get("/api/v1/research/experiment-statistics/deflated-sharpe",
                             params={"experiment_id": ids["other_family"], "family": "mf"})
        no_family = client.get("/api/v1/research/experiment-statistics/deflated-sharpe",
                               params={"experiment_id": ids["with_returns"]})
    assert small.status_code == foreign.status_code == no_family.status_code == 422
    assert small.json()["error"]["code"] == "insufficient_trials"


def test_tail_risk_matches_legacy_page(lab):
    root, ids = lab
    returns = rl.get_experiment(ids["with_returns"])["returns"]
    legacy = portfolio_metrics.tail_risk_metrics(returns, horizon="un trimestre")
    with TestClient(create_app(Settings(root))) as client:
        response = client.get(f"/api/v1/research/experiments/{ids['with_returns']}/tail-risk")
        missing = client.get(f"/api/v1/research/experiments/{ids['summary_only']}/tail-risk")
    assert response.status_code == 200
    body = response.json()
    assert body["horizon"] == "un trimestre"
    summary = body["series"][0]["summary"]
    assert summary["n_obs"] == legacy["n_obs"]
    assert summary["level_95"]["var"] == legacy["95"]["var"]
    assert summary["level_99"]["expected_shortfall"] == legacy["99"]["expected_shortfall"]
    assert summary["skewness"] == legacy["skewness"]
    assert missing.status_code == 422


def test_statistics_require_research_mode(lab):
    root, ids = lab
    (root / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with TestClient(create_app(Settings(root))) as client:
        dsr = client.get("/api/v1/research/experiment-statistics/deflated-sharpe",
                         params={"experiment_id": ids["with_returns"], "family": "mf"})
        tail = client.get(f"/api/v1/research/experiments/{ids['with_returns']}/tail-risk")
    assert dsr.status_code == tail.status_code == 403
