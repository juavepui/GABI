import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi.variant_validation import VariantSpec, run_validation


def _fake_result(start, end, **kwargs):
    dates = []
    current = pd.Timestamp("2016-07-02")
    while current <= pd.Timestamp("2026-04-02"):
        dates.append(current)
        current += pd.DateOffset(months=3)
    periods = pd.DataFrame({"fecha": [d.date().isoformat() for d in dates[:-1]],
                            "hasta": [d.date().isoformat() for d in dates[1:]],
                            "turnover_pct": 10.0, "comision_pagada": 1.0})
    nav = pd.Series(np.linspace(100_000, 150_000, len(dates)), index=dates)
    return {"periods": periods, "nav_curve": nav, "nav_curve_spy": nav * .98}


def test_harness_adds_unchanged_control_and_reports_windows():
    report = run_validation([VariantSpec("hurdle_5", {"rotation_hurdle_points": 5})], runner=_fake_result)
    assert report["variants_declared"] == ["control_composite", "hurdle_5"]
    assert set(report["report"]["window"]) == {"development", "validation", "future"}
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
