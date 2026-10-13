"""Research Lab, blind validation and model status without the storage facade: captured parity (#133)."""

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

import gabi
from gabi import app_mode, blind_validation, config, research_lab, screener_asof, storage
from gabi.infrastructure.providers import research_environment

REFERENCE = json.loads((Path(__file__).parent / "fixtures/research_ledgers_migration.json").read_text(encoding="utf-8"))
NOW = pd.Timestamp("2024-01-02T03:04:05")
TABLES = ("experiments", "blind_validations", "blind_validation_periods", "blind_validation_options",
          "blind_validation_rankings")


def captured(name: str) -> ModuleType:
    module = ModuleType(f"gabi.{name}")
    module.__package__, module.__file__ = "gabi", str(Path(research_lab.__file__).with_name(f"{name}.py"))
    exec(REFERENCE[name], module.__dict__)
    return module


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: NOW))
    for module in (research_lab,):
        monkeypatch.setattr(module, "_current_git_commit", lambda: "abc1234")
        monkeypatch.setattr(module, "_dependency_versions", lambda: {"pandas": "2.x"})
        monkeypatch.setattr(module, "_env_fingerprint", lambda: "deadbeef1234")
    monkeypatch.setattr(blind_validation, "_current_git_commit", lambda: "abc1234")
    old_lab = captured("research_lab")
    for name, value in (("_current_git_commit", lambda: "abc1234"), ("_dependency_versions", lambda: {"pandas": "2.x"}),
                        ("_env_fingerprint", lambda: "deadbeef1234")):
        setattr(old_lab, name, value)
    old_blind = captured("blind_validation")
    old_blind._current_git_commit = lambda: "abc1234"
    old_blind.log_experiment = old_lab.log_experiment
    return {"lab": old_lab, "blind": old_blind, "root": tmp_path}


def use(root: Path, label: str, monkeypatch) -> Path:
    directory = root / label
    monkeypatch.setattr(config, "DATA_DIR", directory)
    monkeypatch.setattr(config, "DB_PATH", directory / "gabi.db")
    return directory / "gabi.db"


def tables(path: Path) -> dict:
    if not path.exists():
        return {}
    with closing(sqlite3.connect(path)) as db:
        present = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        return {table: (db.execute(f"SELECT sql FROM sqlite_schema WHERE name='{table}'").fetchone()[0],
                        db.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall())
                for table in TABLES if table in present}


def outcome(function, *args, **kwargs):
    try:
        value = function(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - type and message are compared
        return ("raised", type(exc).__name__, str(exc))
    if isinstance(value, pd.DataFrame):
        return ("frame", list(value.columns), [str(d) for d in value.dtypes], value.to_json(orient="split"))
    if isinstance(value, dict) and isinstance(value.get("returns"), pd.Series):
        return {**value, "returns": value["returns"].to_json()}
    return value


def lab_session(lab) -> list:
    # Stored out of order: the detail is read back sorted by date.
    returns = pd.Series([0.03, np.nan, -0.02, 0.01], index=pd.to_datetime(["2020-12-31", "2020-06-30",
                                                                          "2020-09-30", "2020-03-31"]))
    calls = [
        (lab.list_experiments,), (lab.get_experiment, 1), (lab.list_families,),
        (lab.log_experiment, "M1", "NOT_A_STAGE", True),
        (lab.log_experiment, "M1", "RESEARCH", True),
        (lab.log_experiment, "M1", "IN_SAMPLE", 0, ),
        (lab.log_experiment, "M2", "OUT_OF_SAMPLE", False),
        (lab.log_experiment, "M3", "LIVE_FORWARD", True),
    ]
    results = [outcome(*call) for call in calls]
    results.append(outcome(lab.log_experiment, "M4", "RESEARCH", True, git_commit="feedbee", data_cutoff="2024-01-01",
                           universe="S&P 500", factors="V/Q", weights={"value": 1.0}, n_positions=20,
                           rebalance="Q", cost_model="10 bps", is_start="2016-01-01", is_end="2020-12-31",
                           oos_start="2021-01-01", oos_end="2023-12-31", family="fam-b", sharpe=0.8, sortino=1.1,
                           max_drawdown=-0.3, total_return=0.5, annualized_return=0.07, periods_per_year=4,
                           n_periods=4, returns=returns, notes="nota", result={"x": [1, 2]},
                           data_fingerprint="v2:abc"))
    results.append(outcome(lab.log_experiment, "M5", "RESEARCH", True, weights={}, result={}, family="fam-a",
                           returns=pd.Series(dtype=float)))
    for family, stage in ((None, None), ("fam-a", None), (None, "RESEARCH"), ("fam-b", "RESEARCH"), ("none", None)):
        results.append(outcome(lab.list_experiments, family, stage))
    results += [outcome(lab.get_experiment, i) for i in range(0, 8)]
    results += [outcome(lab.list_families), outcome(lab.delete_experiment, 2), outcome(lab.delete_experiment, 99),
                outcome(lab.list_experiments)]
    return results


def test_experiment_log_matches_capture(env, monkeypatch):
    runs = {}
    for label, lab in (("old", env["lab"]), ("new", research_lab)):
        path = use(env["root"], label, monkeypatch)
        runs[label] = (lab_session(lab), tables(path))
    assert runs["new"][0] == runs["old"][0]
    assert runs["new"][1] == runs["old"][1]


def test_experiment_reads_do_not_create_the_database(env, monkeypatch):
    path = use(env["root"], "absent", monkeypatch)
    expected = [outcome(research_lab.list_experiments, None, "LIVE_FORWARD"), research_lab.get_experiment(3),
                research_lab.list_families()]
    assert not path.exists()
    use(env["root"], "absent_old", monkeypatch)
    assert expected == [outcome(env["lab"].list_experiments, None, "LIVE_FORWARD"), env["lab"].get_experiment(3),
                        env["lab"].list_families()]


def legacy_table(path: Path) -> None:
    """The published table before deps/python/environment/data columns were added."""
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = research_lab.SCHEMA
    for column in ("deps_json", "python_version", "env_fingerprint", "data_fingerprint"):
        schema = schema.replace(f"    {column} TEXT,\n", "")
    with closing(sqlite3.connect(path)) as db:
        db.executescript(schema)
        db.execute("INSERT INTO experiments (created_at, model_id, git_commit, hypothesis_registered, stage, family, "
                   "returns_json, weights_json) VALUES ('2021-01-01','OLD','0ld',1,'RESEARCH','f',"
                   "'{\"2020-03-31\": 0.1}','{\"value\": 1}')")
        db.commit()


def test_legacy_table_without_late_columns_matches_capture(env, monkeypatch):
    runs = {}
    for label, lab in (("old", env["lab"]), ("new", research_lab)):
        path = use(env["root"], label, monkeypatch)
        legacy_table(path)
        before = path.read_bytes() if label == "new" else None
        reads = [outcome(lab.list_experiments), outcome(lab.get_experiment, 1), outcome(lab.list_families)]
        if label == "new":
            assert path.read_bytes() == before  # reading never alters the published table
        reads.append(outcome(lab.log_experiment, "M", "RESEARCH", True, family="g"))
        reads += [outcome(lab.list_experiments), outcome(lab.get_experiment, 2)]
        runs[label] = (reads, tables(path))
    assert runs["new"] == runs["old"]


def seed_prices(rows: dict) -> None:
    for symbol, values in rows.items():
        index = pd.date_range("2024-01-01", periods=len(values), freq="D")
        frame = pd.DataFrame({"Open": values, "High": values, "Low": values, "Close": values,
                              "Adj Close": values, "Volume": 1e6}, index=index)
        storage.upsert_prices(symbol, frame)


def blind_session(bv) -> list:
    weights = {"value": 1.0, "quality": 0.0, "momentum": 0.0, "risk": 0.0}
    calls = [(bv.list_validations,), (bv.verify_integrity, 1), (bv.get_status, 1), (bv.record_rebalance, 1),
             (bv.enable_ranking_snapshots, 1),
             (bv.create_validation, "Mal", weights, 2, 3, "2024-01-10", "2024-01-10"),
             (bv.create_validation, "Mal", weights, 0, 3, "2024-01-10", "2099-01-01"),
             (bv.create_validation, "Sellada", weights, 2, 3, "2024-01-05", "2099-01-01"),
             (bv.create_validation, "Pasada", weights, 2, 3, "2024-01-05", "2024-01-20", "GABI-VALUE-v1"),
             (bv.enable_ranking_snapshots, 2),
             (bv.record_rebalance, 1, "2024-01-05"), (bv.record_rebalance, 1, "2024-01-05"),
             (bv.record_rebalance, 1, "2024-01-08"), (bv.record_rebalance, 2, "2024-01-06"),
             (bv.record_rebalance, 2, "2024-01-09"), (bv.record_rebalance, 1, "2024-01-30"),
             (bv.verify_integrity, 1), (bv.verify_integrity, 2),
             (bv.get_status, 1), (bv.get_status, 1, True), (bv.get_status, 1, True, "2024-01-07"),
             (bv.get_status, 2), (bv.get_status, 2, False, "2024-01-08"), (bv.get_status, 99),
             (bv.export_to_research_lab, 1), (bv.break_seal_early, 1, "  "),
             (bv.break_seal_early, 1, "Prueba de ruptura"), (bv.get_status, 1),
             (bv.export_to_research_lab, 1), (bv.export_to_research_lab, 2, "2024-01-08"),
             (bv.export_to_research_lab, 99), (bv.list_validations,)]
    return [outcome(*call) for call in calls]


def test_blind_validation_matches_capture(env, monkeypatch):
    def rank(day, symbols=None, weights=None):
        # Before the 7th the best score lacks coverage and must not be picked.
        if day < "2024-01-07":
            scores, coverage = {"C": 95, "A": 90, "B": 80, "D": 70}, [.4, .9, .9, .95]
        else:
            scores, coverage = {"A": 60, "B": 85, "C": 75, "D": None}, [.9, .9, .8, .95]
        return {"table": pd.DataFrame({"composite_score": list(scores.values()), "score_coverage": coverage},
                                      index=list(scores))}
    monkeypatch.setattr(screener_asof, "build_ranking_as_of", rank)
    runs = {}
    for label, bv in (("old", env["blind"]), ("new", blind_validation)):
        path = use(env["root"], label, monkeypatch)
        storage.init_db()
        seed_prices({"A": [100.0 + i for i in range(30)], "B": [50.0] * 8 + [55.0] * 22,
                     "C": [20.0] * 30, "SPY": [400.0 + 2 * i for i in range(30)]})
        runs[label] = (blind_session(bv), tables(path))
    assert runs["new"][0] == runs["old"][0]
    assert runs["new"][1] == runs["old"][1]


def test_blind_reads_never_create_the_database(env, monkeypatch):
    path = use(env["root"], "absent", monkeypatch)
    results = [outcome(blind_validation.list_validations), outcome(blind_validation.verify_integrity, 1),
               outcome(blind_validation.get_status, 1), outcome(blind_validation.export_to_research_lab, 1)]
    assert not path.exists()
    use(env["root"], "absent_old", monkeypatch)
    assert results == [outcome(env["blind"].list_validations), outcome(env["blind"].verify_integrity, 1),
                       outcome(env["blind"].get_status, 1), outcome(env["blind"].export_to_research_lab, 1)]


@pytest.mark.parametrize("scenario", ["empty", "weak", "strong", "broken", "other_weights", "no_periods"])
def test_model_status_matches_capture(env, monkeypatch, scenario):
    frozen = dict(app_mode.FROZEN_WEIGHTS)
    other = {"value": 1.0, "quality": 0.0, "momentum": 0.0, "risk": 0.0}
    monkeypatch.setattr(screener_asof, "build_ranking_as_of", lambda day, symbols=None, weights=None: {
        "table": pd.DataFrame({"composite_score": [90.0], "score_coverage": [.9]}, index=["A"])})
    results = {}
    for label in ("old", "new"):
        path = use(env["root"], label, monkeypatch)
        monkeypatch.setattr(config, "load_weights", lambda: dict(frozen))
        if scenario != "empty":
            storage.init_db()
            seed_prices({"A": [10.0] * 5})
        if scenario == "weak":
            research_lab.log_experiment("M", "LIVE_FORWARD", True)
        if scenario in {"strong", "broken", "other_weights", "no_periods"}:
            vid = blind_validation.create_validation("V", other if scenario == "other_weights" else frozen, 1, 3,
                                                     "2024-01-01", "2099-01-01")
            if scenario != "no_periods":
                blind_validation.record_rebalance(vid, "2024-01-03")
            if scenario == "broken":
                blind_validation.break_seal_early(vid, "motivo")
        if label == "old":
            monkeypatch.setattr(gabi, "research_lab", env["lab"])
            monkeypatch.setattr(gabi, "blind_validation", env["blind"])
            monkeypatch.setitem(sys.modules, "gabi.research_lab", env["lab"])
            monkeypatch.setitem(sys.modules, "gabi.blind_validation", env["blind"])
            results[label] = captured("app_mode").current_model_status()
            monkeypatch.setattr(gabi, "research_lab", research_lab)
            monkeypatch.setattr(gabi, "blind_validation", blind_validation)
            monkeypatch.setitem(sys.modules, "gabi.research_lab", research_lab)
            monkeypatch.setitem(sys.modules, "gabi.blind_validation", blind_validation)
        else:
            before = path.read_bytes() if path.exists() else None
            results[label] = app_mode.current_model_status()
            assert (path.read_bytes() if path.exists() else None) == before
    assert results["new"] == results["old"]


def test_environment_provider_matches_capture(tmp_path, monkeypatch):
    lab = captured("research_lab")
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    assert research_lab._env_fingerprint() is None and lab._env_fingerprint() is None
    (tmp_path / "uv.lock").write_bytes(b"version = 1\n")
    assert research_lab._env_fingerprint() == lab._env_fingerprint()
    assert research_lab._dependency_versions() == lab._dependency_versions()
    assert research_lab._current_git_commit() == lab._current_git_commit()  # tmp_path is not a checkout: None
    assert research_environment.dependency_versions(["pandas", "not-a-gabi-package"]) == {"pandas": pd.__version__}


def test_facades_no_longer_import_storage_sqlite_or_subprocess():
    import ast

    for module in (research_lab, blind_validation, app_mode):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        names |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and not node.level}
        names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level
                  for alias in node.names}
        forbidden = {"storage", "sqlite3", "subprocess", "importlib.metadata"}
        if module is app_mode:
            forbidden |= {"research_lab", "blind_validation"}
        assert not names & forbidden, module.__name__
