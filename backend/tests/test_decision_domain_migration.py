"""Decision rules and saved-table compatibility after removing the flat module."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from gabi.domain.portfolio import decisions
from gabi.infrastructure.serialization.decisions import build_decisions
from gabi.infrastructure.storage.decisions import SqliteDecisions

CASES = ("normal", "absent_prices", "low_score", "low_coverage", "below_sma", "high_risk", "protected_holding")


def decision_inputs(case):
    dates = pd.bdate_range(end="2026-09-10", periods=180)
    history = pd.DataFrame({"adj_close": [100 + i * .1 for i in range(180)]}, index=dates)
    table = pd.DataFrame({"composite_score": [80.], "score_coverage": [.9], "price_vs_sma200": [.1],
                          "volatility": [.2], "max_drawdown": [-.2], "sector": ["Tech"]}, index=["AAA"])
    histories, holdings = {"AAA": history}, {"AAA": 1.}
    if case == "absent_prices":
        histories = {}
    elif case == "low_score":
        table.loc["AAA", "composite_score"] = 50.
    elif case == "low_coverage":
        table.loc["AAA", "score_coverage"] = .3
    elif case == "below_sma":
        table.loc["AAA", "price_vs_sma200"] = -.1
    elif case == "high_risk":
        table.loc["AAA", "volatility"] = .8
    elif case == "protected_holding":
        holdings = {"UNKNOWN": 98.}
    return table, histories, holdings


@pytest.mark.parametrize("case", CASES)
def test_rules_match_original_reference(case):
    reference = json.loads((Path(__file__).parent / "fixtures/decision_rules_migration.json").read_text(encoding="utf-8"))
    table, histories, holdings = decision_inputs(case)
    result = build_decisions(table, histories, holdings, {}, "2026-09-10")
    expected = reference[case]
    for key in ("decisions", "targets", "rejections", "method", "cash_target_pct", "policy", "holdings", "status"):
        assert result[key] == expected[key]
    assert result["risk"].keys() == expected["risk"].keys()
    for key, value in expected["risk"].items():
        if isinstance(value, float):
            assert result["risk"][key] == pytest.approx(value, rel=1e-12, abs=1e-14)
        else:
            assert result["risk"][key] == value


def test_decision_day_is_required_and_inputs_are_unchanged():
    table, histories, holdings = decision_inputs("normal")
    before = table.copy(deep=True)
    history = histories["AAA"].copy(deep=True)
    with pytest.raises(TypeError, match="as_of"):
        decisions.build_plan(table, histories, holdings)
    decisions.build_plan(table, histories, holdings, as_of="2026-09-10")
    pd.testing.assert_frame_equal(table, before)
    pd.testing.assert_frame_equal(histories["AAA"], history)
    assert holdings == {"AAA": 1.}


def test_two_repositories_receive_independent_paths_and_clocks(tmp_path):
    left = SqliteDecisions(tmp_path / "left", now=lambda: datetime(2020, 1, 2, tzinfo=UTC))
    right = SqliteDecisions(tmp_path / "right", now=lambda: datetime(2024, 3, 4, tzinfo=UTC))
    record = {"decisions": [], "method": "fixture", "policy": {}, "holdings": {}}
    first = left.save(record, "Izquierda", "job")
    second = right.save(record, "Derecha", "job")
    assert left.get(first)["created_at"] == "2020-01-02T00:00:00+00:00"
    assert right.get(second)["created_at"] == "2024-03-04T00:00:00+00:00"
    assert left.get(first)["name"] == "Izquierda" and right.get(second)["name"] == "Derecha"


def test_reading_old_saved_table_does_not_migrate_or_write(tmp_path):
    path = tmp_path / "gabi.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE decision_runs(id INTEGER PRIMARY KEY, created_at TEXT, method TEXT, "
                   "decisions_json TEXT, policy_json TEXT, holdings_json TEXT)")
        db.execute("INSERT INTO decision_runs VALUES(1,'2024-01-02','fixture','[]','{}','{}')")
    before = path.read_bytes()
    repo = SqliteDecisions(tmp_path)
    assert repo.list()[0]["name"] == "Plan #1"
    assert repo.get(1)["decisions"] == []
    assert path.read_bytes() == before
    assert repo.rename(1, "Actualizado")
    assert repo.get(1)["name"] == "Actualizado"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT method FROM decision_runs WHERE id=1").fetchone()[0] == "fixture"
