"""Plausibility checks input-checks-v1 (#295): impossible values, limits, a real split and the checked scoring."""

import pandas as pd
import pytest

from gabi.domain.market import input_checks as checks
from gabi.infrastructure.legacy.market import calculators
from gabi.infrastructure.model_versions import GABI_MF_V1, GABI_MF_V2, GABI_MF_V3


def test_impossible_yahoo_values_are_marked_and_limits_pass():
    marks = checks.check_fields({"pe": 40000.0, "operating_margin": 3.0, "roe": 0.2, "pb": float("nan"),
                                 "debt_to_equity": -5.0, "gross_margin": None})
    assert {(mark["field"], mark["rule"]) for mark in marks} == {
        ("pe", "range"), ("operating_margin", "range"), ("pb", "range"), ("debt_to_equity", "range")}
    assert next(mark for mark in marks if mark["field"] == "pb")["reason"] == "No es un número finito"
    # Both ends of every range are plausible: a 100 % margin or a PER of exactly 1 000 is kept.
    limits = {field: high for field, (low, high) in checks.RANGES.items()}
    assert checks.check_fields(limits) == []
    assert checks.check_fields({field: low for field, (low, high) in checks.RANGES.items()}) == []
    assert checks.check_fields({"pe": 1000.0001})[0]["field"] == "pe"


def prices(closes, start="2024-06-03"):
    days = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"close": closes, "adj_close": closes}, index=days)


def test_a_jump_without_split_is_marked_and_a_real_split_is_not():
    # +80 % in one session with nothing recorded: marked.
    jump = checks.check_jumps(prices([100.0, 101.0, 181.8, 182.0]))
    assert len(jump) == 1 and jump[0]["value"] == pytest.approx(0.8) and jump[0]["date"] == "2024-06-05"
    # Apple's 4:1 split of 2020-08-31 on unadjusted closes (499.23 → 129.04): recorded, so not marked.
    split = pd.DataFrame({"close": [499.23, 129.04, 134.18]}, index=pd.to_datetime(["2020-08-28", "2020-08-31",
                                                                                      "2020-09-01"]))
    assert checks.check_jumps(split, ["2020-08-31"]) == []
    assert len(checks.check_jumps(split)) == 1  # The same move with no split recorded would be marked.
    # Exactly 50 % is the limit and stays unmarked.
    assert checks.check_jumps(prices([100.0, 150.0])) == []


def test_the_market_cap_cross_check_only_informs_beyond_its_tolerance():
    assert checks.check_market_cap(1.4e9, 10.0, 1e8) is None  # +40 %: within ±50 %.
    far = checks.check_market_cap(1.6e12, 10.0, 1e8)
    assert far["rule"] == "market_cap" and far["gap"] == pytest.approx(1599.0)
    assert checks.check_market_cap(None, 10.0, 1e8) is None and checks.check_market_cap(1e9, 10.0, None) is None
    # It never drops a scored field.
    assert checks.apply({"pe": 12.0, "market_cap": 1.6e12}, [far]) == {"pe": 12.0, "market_cap": 1.6e12}


def test_a_marked_value_is_scored_as_missing_and_a_jump_drops_the_price_metrics():
    metrics = {"pe": 40000.0, "pb": 2.0, "momentum_12m": 0.3, "volatility": 0.2}
    assert checks.apply(metrics, checks.check_fields(metrics)) == {**metrics, "pe": None}
    jumped = checks.apply(metrics, [{"rule": "jump", "field": "price"}])
    assert jumped["momentum_12m"] is None and jumped["volatility"] is None and jumped["pe"] == 40000.0


def test_only_v3_scores_with_the_checks():
    assert GABI_MF_V1.input_checks is None and GABI_MF_V2.input_checks is None
    assert GABI_MF_V3.input_checks == checks.VERSION
    record = {"info": {"trailingPE": 40000.0, "priceToBook": 2.0}, "quarterly_income": {}}
    plain = calculators(GABI_MF_V2.technical)
    checked = calculators(GABI_MF_V3.technical, input_checks=GABI_MF_V3.input_checks)
    assert plain.fundamentals(record)["pe"] == 40000.0
    assert checked.fundamentals(record)["pe"] is None and checked.fundamentals(record)["pb"] == 2.0
    with pytest.raises(ValueError):
        calculators(GABI_MF_V2.technical, input_checks="input-checks-v9")


def test_the_report_job_lists_marks_over_the_cached_universe_without_writing(tmp_path):
    import json
    import sqlite3
    from contextlib import closing

    from market_fixture import TODAY, seed_fixture

    from gabi.application.administration.jobs import JobCommand
    from gabi.infrastructure.legacy.jobs import LegacyExecutor
    from gabi.infrastructure.settings import Settings

    seed_fixture(tmp_path)
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db, db:
        info = json.loads(db.execute("SELECT info_json FROM fundamentals WHERE symbol='T001'").fetchone()[0])
        db.execute("UPDATE fundamentals SET info_json=? WHERE symbol='T001'",
                   (json.dumps(info | {"trailingPE": 40000, "operatingMargins": 3.0}),))
    stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
    result = LegacyExecutor(Settings(tmp_path), today=lambda: TODAY)(JobCommand("input_checks"))
    # GABI-MF-v5 (#347) scores as the tested engine did, without the checks: the report only warns.
    assert result["policy"] == "input-checks-v1" and result["model_id"] == "GABI-MF-v5" and not result["applied"]
    marked = {(mark["symbol"], mark["field"]) for mark in result["marks"]}
    assert {("T001", "pe"), ("T001", "operating_margin")} <= marked
    assert result["by_field"]["pe"] >= 1 and result["companies"] == 16
    assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp
