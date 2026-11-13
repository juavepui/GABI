"""Manual Research Lab records and deletions are explicit Research commands with the Streamlit fields."""

import pytest
from fastapi.testclient import TestClient

from gabi import config
from gabi import research_lab as rl
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app

FORM = {"model_id": "GABI-MF-v1.0", "n_positions": 20, "rebalance": "Quarterly",
        "universe": "S&P 500 histórico, muestra de 200", "cost_model": "10pb por lado", "family": "manual",
        "data_cutoff": "2026-09-30", "is_start": "2016-07-02", "is_end": "2025-04-01", "sharpe": 0.62,
        "sortino": 0.0, "max_drawdown": -0.25, "n_periods": 36, "periods_per_year": 4.0, "stage": "IN_SAMPLE",
        "hypothesis_registered": True, "data_fingerprint": "  fp-manual  ", "notes": ""}


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(rl, "_current_git_commit", lambda: "abc1234")
    (tmp_path / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    return tmp_path


def test_manual_experiment_matches_the_streamlit_form(root):
    with TestClient(create_app(Settings(root))) as client:
        response = client.post("/api/v1/research/experiments", json=FORM)
    assert response.status_code == 201
    created = rl.get_experiment(response.json()["id"])
    expected_id = rl.log_experiment(  # The call of app/pages/11_Research_Lab.py before its retirement.
        "GABI-MF-v1.0", "IN_SAMPLE", True, data_cutoff="2026-09-30", data_fingerprint="fp-manual",
        universe="S&P 500 histórico, muestra de 200", factors="Value/Quality/Momentum/Risk", n_positions=20,
        rebalance="Quarterly", cost_model="10pb por lado", is_start="2016-07-02", is_end="2025-04-01",
        family="manual", sharpe=0.62, sortino=None, max_drawdown=-0.25, n_periods=36, periods_per_year=4.0,
        notes=None)
    expected = rl.get_experiment(expected_id)
    for key in set(expected) - {"id", "created_at"}:
        assert created[key] == expected[key], key
    assert response.json()["sortino"] is None and response.json()["git_commit"] == "abc1234"


def test_delete_is_explicit_and_reports_missing_experiments(root):
    experiment_id = rl.log_experiment("M", "RESEARCH", False)
    with TestClient(create_app(Settings(root))) as client:
        deleted = client.post(f"/api/v1/research/experiments/{experiment_id}/delete")
        again = client.post(f"/api/v1/research/experiments/{experiment_id}/delete")
    assert deleted.json() == {"deleted": experiment_id}
    assert again.status_code == 404 and again.json()["error"]["message"] == f"No existe el experimento #{experiment_id}."
    assert rl.get_experiment(experiment_id) == {}


@pytest.mark.parametrize("change", [{"stage": "BOGUS"}, {"rebalance": "Weekly"}, {"n_positions": 0},
                                    {"model_id": " "}, {"data_cutoff": "2026-13-01"}, {"sharpe": "x"}])
def test_invalid_forms_write_nothing(root, change):
    with TestClient(create_app(Settings(root))) as client:
        response = client.post("/api/v1/research/experiments", json=FORM | change)
    assert response.status_code == 422
    assert not (root / "gabi.db").exists()


def test_writes_require_research_mode_and_the_api_data_directory(root, tmp_path_factory, monkeypatch):
    experiment_id = rl.log_experiment("M", "RESEARCH", False)
    (root / "app_mode.json").write_text('{"mode":"INVESTOR"}')
    with TestClient(create_app(Settings(root))) as client:
        assert client.post("/api/v1/research/experiments", json=FORM).status_code == 403
        assert client.post(f"/api/v1/research/experiments/{experiment_id}/delete").status_code == 403
    (root / "app_mode.json").write_text('{"mode":"RESEARCH"}')
    monkeypatch.setattr(config, "DATA_DIR", tmp_path_factory.mktemp("other"))
    with TestClient(create_app(Settings(root))) as client:
        assert client.post(f"/api/v1/research/experiments/{experiment_id}/delete").status_code == 503
    assert rl.get_experiment(experiment_id) != {}
