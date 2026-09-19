import platform
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config
from gabi import research_lab as rl


def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")


def test_log_experiment_rejects_unknown_stage(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        rl.log_experiment("GABI-MF-v1", "BOGUS_STAGE", True)


def test_log_experiment_captures_git_commit_when_not_given(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    monkeypatch.setattr(rl, "_current_git_commit", lambda: "abc1234")
    exp_id = rl.log_experiment("GABI-MF-v1", "RESEARCH", True, sharpe=0.71)
    row = rl.get_experiment(exp_id)
    assert row["git_commit"] == "abc1234"


def test_log_experiment_uses_explicit_git_commit_without_calling_current(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)

    def _boom():
        raise AssertionError("no deberia llamarse si se pasa git_commit explicito")

    monkeypatch.setattr(rl, "_current_git_commit", _boom)
    exp_id = rl.log_experiment("GABI-MF-v1", "RESEARCH", True, git_commit="deadbee", sharpe=0.71)
    assert rl.get_experiment(exp_id)["git_commit"] == "deadbee"


def test_log_and_get_experiment_roundtrips_all_fields(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    returns = pd.Series([0.01, -0.02, 0.03], index=pd.to_datetime(["2024-01-01", "2024-04-01", "2024-07-01"]))
    exp_id = rl.log_experiment(
        "GABI-MF-v2.0", "IN_SAMPLE", True, git_commit="abc1234", data_cutoff="2026-09-17",
        universe="S&P 500 PIT", factors="Value/Quality/Momentum/Risk", weights={"value": .3, "quality": .35},
        n_positions=20, rebalance="Quarterly", cost_model="turnover + spread",
        is_start="2016-07-02", is_end="2025-04-01", family="posiciones_frecuencia_v1",
        sharpe=0.71, sortino=1.00, max_drawdown=-0.378, total_return=3.564,
        annualized_return=0.183, periods_per_year=4, n_periods=36, returns=returns,
        notes="Top-20 trimestral, hipotesis congelada", result={"extra": "dato libre"},
    )
    row = rl.get_experiment(exp_id)
    assert row["model_id"] == "GABI-MF-v2.0"
    assert row["stage"] == "IN_SAMPLE"
    assert row["hypothesis_registered"] == 1
    assert row["weights"] == {"value": .3, "quality": .35}
    assert row["result"] == {"extra": "dato libre"}
    assert row["n_periods"] == 36
    pd.testing.assert_series_equal(row["returns"], returns.sort_index(), check_names=False)


def test_log_experiment_captures_python_version_and_env_fingerprint(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    monkeypatch.setattr(rl, "_env_fingerprint", lambda: "deadbeef1234")
    exp_id = rl.log_experiment("A", "RESEARCH", True)
    row = rl.get_experiment(exp_id)
    assert row["python_version"] == platform.python_version()
    assert row["env_fingerprint"] == "deadbeef1234"


def test_env_fingerprint_is_stable_for_same_lockfile_and_changes_with_it(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    lock = tmp_path / "uv.lock"
    lock.write_text("version = 1\n")
    first = rl._env_fingerprint()
    assert first == rl._env_fingerprint()  # mismo contenido -> mismo fingerprint

    lock.write_text("version = 2\n")
    assert rl._env_fingerprint() != first  # lockfile distinto -> fingerprint distinto


def test_env_fingerprint_is_none_without_lockfile(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)  # sin uv.lock aquí
    assert rl._env_fingerprint() is None


def test_get_experiment_missing_id_returns_empty_dict(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    assert rl.get_experiment(999) == {}


def test_list_experiments_filters_by_family_and_stage(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    rl.log_experiment("A", "RESEARCH", True, family="fam1", sharpe=0.5)
    rl.log_experiment("B", "RESEARCH", True, family="fam2", sharpe=0.6)
    rl.log_experiment("C", "IN_SAMPLE", True, family="fam1", sharpe=0.7)

    assert len(rl.list_experiments()) == 3
    assert len(rl.list_experiments(family="fam1")) == 2
    assert len(rl.list_experiments(stage="IN_SAMPLE")) == 1
    assert len(rl.list_experiments(family="fam1", stage="RESEARCH")) == 1


def test_delete_experiment_removes_it_and_returns_true(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    exp_id = rl.log_experiment("A", "RESEARCH", True)
    assert rl.delete_experiment(exp_id) is True
    assert rl.get_experiment(exp_id) == {}


def test_delete_experiment_returns_false_for_missing_id(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    assert rl.delete_experiment(999) is False


def test_list_families_returns_distinct_non_null_families(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    rl.log_experiment("A", "RESEARCH", True, family="fam1")
    rl.log_experiment("B", "RESEARCH", True, family="fam1")
    rl.log_experiment("C", "RESEARCH", True, family="fam2")
    rl.log_experiment("D", "RESEARCH", True)  # sin familia
    assert rl.list_families() == ["fam1", "fam2"]
