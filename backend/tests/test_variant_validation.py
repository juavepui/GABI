import sys
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi.variant_validation import DEFAULT_END, DEFAULT_START, VariantSpec, _window_metrics, run_validation


def _fake_result(start, end, **kwargs):
    dates = []
    current = pd.Timestamp(DEFAULT_START)
    while current <= pd.Timestamp(DEFAULT_END):
        dates.append(current)
        current += pd.DateOffset(months=3)
    periods = pd.DataFrame({"fecha": [d.date().isoformat() for d in dates[:-1]],
                            "hasta": [d.date().isoformat() for d in dates[1:]],
                            "turnover_pct": 10.0, "comision_pagada": 1.0,
                            "spread_pagado": 2.0, "coste_total": 3.0})
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2016-01-04", DEFAULT_END)
    nav = pd.Series(np.linspace(99_000, 150_000, len(sessions)), index=sessions)
    return {"periods": periods, "nav_curve": nav, "nav_curve_spy": nav * .98,
            "initial_capital": 100_000.}


def test_harness_adds_unchanged_control_and_reports_windows():
    report = run_validation([VariantSpec("hurdle_5", {"rotation_hurdle_points": 5})], runner=_fake_result)
    assert report["variants_declared"] == ["control_composite", "hurdle_5"]
    assert set(report["report"]["window"]) == {
        "full_history", "development_retrospective", "validation_retrospective"}
    assert report["future"]["status"] == "not_evaluated"
    assert (report["report"]["n_obs"] > 0).all()


def test_variant_cannot_change_universe_protocol():
    with pytest.raises(ValueError, match="muestra"):
        VariantSpec("bad", {"max_symbols": 200})


def test_harness_rejects_missing_periods():
    def incomplete(*args, **kwargs):
        result = _fake_result(*args, **kwargs)
        return {**result, "periods": result["periods"].iloc[:-1]}

    with pytest.raises(ValueError, match="39 rebalanceos"):
        run_validation([VariantSpec("x")], runner=incomplete)


def test_window_includes_initial_cost_and_every_rebalance_once():
    result = _fake_result(DEFAULT_START, DEFAULT_END)
    full = _window_metrics(result, DEFAULT_START, DEFAULT_END)
    first = _window_metrics(result, DEFAULT_START, "2021-01-02")
    second = _window_metrics(result, "2021-01-02", DEFAULT_END)
    assert full["initial_value"] == 100_000
    years = (result["nav_curve"].index[-1] - result["nav_curve"].index[0]).days / 365.25
    assert full["cagr_net"] == pytest.approx(1.5 ** (1 / years) - 1)
    assert full["drawdown"] == pytest.approx(-.01)
    assert first["n_obs"] + second["n_obs"] == full["n_obs"]
    assert first["n_periods"] == 20
    assert second["n_periods"] == 19
    assert first["cost_total"] + second["cost_total"] == full["cost_total"] == 117
    assert first["final_value"] == second["initial_value"]


def test_same_count_but_different_dates_rejected_before_execution():
    with pytest.raises(ValueError, match="fechas"):
        run_validation([VariantSpec("x")], start="2016-07-02", end="2026-04-02", runner=_fake_result)
