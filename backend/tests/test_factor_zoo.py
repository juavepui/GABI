"""Contratos estadísticos de STAT-5 (#48)."""

import json

import numpy as np
import pandas as pd
import pytest

from gabi import factor_zoo as zoo


def test_factor_list_and_preregistration_are_frozen():
    record = json.loads((zoo.OUTPUT / "preregistro.json").read_text(encoding="utf-8"))
    assert record["sha256"] == zoo.spec_hash()
    assert len(zoo.SIGNALS) == 13
    assert {x[2] for x in zoo.SIGNALS} == {"lower", "higher"}


def test_calendar_hac_preserves_missing_quarter_lags():
    with_gap = pd.Series([1., 2., np.nan, 2.] * 10)
    compressed = with_gap.dropna().reset_index(drop=True)
    result = zoo._hac_calendar(with_gap)
    assert result["n"] == 30
    assert result["media"] == pytest.approx(5 / 3)
    assert result["se_hac"] != pytest.approx(zoo._hac_calendar(compressed)["se_hac"])


def test_signal_rows_recover_known_rank_signal():
    n = 300
    score = np.linspace(0, 100, n)
    frame = pd.DataFrame({"pe_pct": score, "retorno": score / 1000,
                          "sector": ["A"] * n, "market_cap": np.arange(n) + 100},
                         index=[f"S{i:03d}" for i in range(n)])
    row, quantiles, stability = zoo._signal_rows(frame, "2020-01-02", "pe")
    assert row["ic"] == pytest.approx(1.)
    assert row["q_spread"] > 0 and row["d_spread"] > 0
    assert len(quantiles) == 15
    assert {x["group"] for x in stability if x["group_type"] == "size"} == {"small", "middle", "large"}
