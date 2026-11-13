"""Nulos de STAT-6: reproducibilidad y detección sintética."""

import json

import numpy as np
import pandas as pd

from gabi import placebo_engine as placebo


def _panels(*, signal: bool) -> list[pd.DataFrame]:
    rng = np.random.default_rng(202)
    panels = []
    for period, date in enumerate(pd.date_range("2016-01-02", periods=12, freq="QS")):
        score = rng.normal(size=80)
        shock = rng.normal(0.01, .015)
        returns = shock + rng.normal(0, .03, size=80)
        if signal:
            returns += .04 * score
        frame = pd.DataFrame({"composite_score": score, "retorno": returns,
                              "sector": ["A"] * 40 + ["B"] * 40,
                              **{block: score + rng.normal(0, .2, size=80) for block in placebo.BLOCKS}},
                             index=[f"S{i:03d}" for i in range(80)])
        frame.attrs["date"] = date.date().isoformat()
        panels.append(frame)
    return panels


def test_preregistration_and_weight_draws_are_fixed():
    record = json.loads((placebo.OUTPUT / "preregistro.json").read_text(encoding="utf-8"))
    assert record["sha256"] == placebo.spec_hash()
    draws = placebo._weight_draws(np.random.default_rng(49), 20)
    assert np.allclose(draws.sum(axis=1), 1)
    assert np.max(np.abs(draws - np.asarray(placebo.BASE_WEIGHTS))) <= .02500001


def test_placebos_detect_known_signal_but_not_random_strategy():
    windows = (("2016-01-01", "2017-01-01"), ("2017-01-01", "2018-01-01"),
               ("2018-01-01", "2019-01-01"))
    known = placebo.simulate(_panels(signal=True), top_n=10, n_simulations=128,
                             seed=17, windows=windows, n_weight_draws=16)
    random = placebo.simulate(_panels(signal=False), top_n=10, n_simulations=128,
                              seed=17, windows=windows, n_weight_draws=16)
    assert known["nulls"]["random_top_n"]["metrics"]["excess_mean"]["p_empirical"] < .05
    assert random["nulls"]["random_top_n"]["metrics"]["excess_mean"]["p_empirical"] > .05
    assert len(known["null_rows"]) == 4 * 128
    assert known["observed"]["excess_mean"] > random["observed"]["excess_mean"]


def test_sector_neutral_draws_preserve_exposure():
    groups = {"A": np.arange(0, 30), "B": np.arange(30, 80)}
    counts = {"A": 7, "B": 3}
    rng = np.random.default_rng(9)
    draws = [placebo._sector_sample(groups, counts, rng) for _ in range(100)]
    assert all(len(set(draw)) == 10 for draw in draws)
    assert all(sum(i < 30 for i in draw) == 7 for draw in draws)
