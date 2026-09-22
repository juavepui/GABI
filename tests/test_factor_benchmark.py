import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gabi import academic_factors as af
from gabi import factor_benchmark as fb


def sample(n=36):
    rng = np.random.default_rng(53)
    dates = pd.date_range("2016-07-01", periods=n + 1, freq="3MS")
    frame = pd.DataFrame(rng.normal(.01, .04, (n, 6)), columns=af.DEFAULT_FACTOR_COLS)
    frame["fecha"], frame["hasta"] = dates[:-1], dates[1:]
    frame["RF"] = .005
    frame["spy"] = frame["RF"] + frame["Mkt-RF"] + rng.normal(0, .005, n)
    frame["excess_return"] = .007 + 1.2 * (frame.spy - frame.RF) + .2 * frame.HML
    frame["retorno"] = frame.excess_return + frame.RF
    frame["universo_ew"] = .9 * frame.spy
    return frame


def test_spy_benchmark_is_rf_plus_beta_excess_excludes_intercept():
    frame = sample()
    frame["retorno"] = frame.RF + .012 + 1.3 * (frame.spy - frame.RF)
    frame["excess_return"] = frame.retorno - frame.RF
    result = fb.analyze(frame)
    fit = result["in_sample"]["regressions"]["spy_beta"]
    assert fit["coef"]["alpha"] == pytest.approx(.012)
    assert fit["coef"]["SPY-RF"] == pytest.approx(1.3)
    for raw, row in zip(frame.itertuples(), result["in_sample"]["periods"]):
        assert row["returns"]["spy_beta"] == pytest.approx(raw.RF + 1.3 * (raw.spy - raw.RF))
        assert row["active"]["spy_beta"] == pytest.approx(.012)


def test_factor_benchmark_recovers_known_loadings_without_adding_alpha():
    frame = sample()
    betas = np.array([1.1, .2, -.1, .3, 0, -.15])
    frame["excess_return"] = .01 + frame[af.DEFAULT_FACTOR_COLS].to_numpy() @ betas
    frame["retorno"] = frame.RF + frame.excess_return
    full = fb.analyze(frame)["in_sample"]
    for i, row in enumerate(full["periods"]):
        expected = frame.RF.iloc[i] + frame[af.DEFAULT_FACTOR_COLS].iloc[i].to_numpy() @ betas
        assert row["returns"]["ff6"] == pytest.approx(expected)
        assert row["active"]["ff6"] == pytest.approx(.01)
    assert full["active"]["ff6"]["mean_active_per_quarter"] == pytest.approx(.01)
    assert full["regressions"]["ff6"]["coef"]["alpha"] == pytest.approx(.01)


def test_expanding_uses_only_mature_prior_observations_and_honors_embargo():
    frame = sample()
    result = fb.analyze(frame)["expanding"]
    assert result["n_obs"] == 17
    assert len(result["coefficients"]) == 34
    assert result["start"] == frame.fecha.iloc[19].date().isoformat()
    for row in result["coefficients"]:
        i = int(frame.index[frame.fecha == row["evaluation_start"]][0])
        training = frame.iloc[:i - 1]
        assert row["n_train"] == len(training)
        assert pd.Timestamp(row["train_end"]) < pd.Timestamp(row["evaluation_start"])
        cols = fb.MODELS[row["model"]]
        training = training.assign(**{"SPY-RF": training.spy - training.RF})
        X = np.column_stack([np.ones(len(training)), training[cols]])
        expected = np.linalg.lstsq(X, training.excess_return.to_numpy(), rcond=None)[0]
        np.testing.assert_allclose(list(row["coef"].values()), expected, atol=1e-12)


def test_target_and_future_strategy_returns_cannot_change_earlier_predictions():
    frame = sample()
    before = fb.analyze(frame)
    frame.loc[25:, "retorno"] += .10
    frame.loc[25:, "excess_return"] += .10
    after = fb.analyze(frame)
    # El retorno cambiado en 25 solo puede entrar en entrenamiento desde 27.
    for a, b in zip(before["expanding"]["periods"], after["expanding"]["periods"]):
        if a["fecha"] <= frame.fecha.iloc[26].date().isoformat():
            for model in fb.MODELS:
                assert a["returns"][model] == b["returns"][model]


def test_curves_start_at_one_same_date_and_compound_actual_returns():
    result = fb.analyze(sample())
    for protocol in ("in_sample", "expanding"):
        comparison = result[protocol]
        curves = fb.curve_table(comparison)
        assert (curves.iloc[0] == 1).all()
        assert len(curves) == comparison["n_obs"] + 1
        for name in comparison["metrics"]:
            product = np.prod([1 + row["returns"][name] for row in comparison["periods"]])
            assert curves[name].iloc[-1] == pytest.approx(product)
            assert comparison["metrics"][name]["cagr"] == pytest.approx(product ** (4 / comparison["n_obs"]) - 1)
        for name in fb.MODELS:
            assert comparison["active"][name]["relative_wealth_return"] == pytest.approx(
                curves.strategy.iloc[-1] / curves[name].iloc[-1] - 1,
            )


def test_small_samples_do_not_pad_training_with_zero_benchmark_returns():
    result = fb.analyze(sample(19))
    assert result["expanding"]["status"] == "insufficient_history"
    assert result["expanding"]["n_obs"] == 0
    assert result["expanding"]["coefficients"] == []
    assert fb.analyze(sample(20))["expanding"]["n_obs"] == 1
    with pytest.raises(ValueError, match="18"):
        fb.analyze(sample(17))


@pytest.mark.parametrize("problem", ["missing_spy", "nan", "loss", "duplicate", "gap", "singular"])
def test_rejects_invalid_or_incomparable_inputs(problem):
    frame = sample()
    if problem == "missing_spy":
        frame = frame.drop(columns="spy")
    elif problem == "nan":
        frame.loc[5, "spy"] = np.nan
    elif problem == "loss":
        frame.loc[5, "universo_ew"] = -1
    elif problem == "duplicate":
        frame = pd.concat([frame, frame.iloc[[0]]])
    elif problem == "gap":
        frame = frame.drop(5)
    else:
        frame["spy"] = frame.RF
    with pytest.raises(ValueError):
        fb.analyze(frame)


def test_no_silent_clipping_when_synthetic_benchmark_loses_more_than_capital():
    frame = sample()
    benchmarks = pd.DataFrame({"spy_beta": np.full(36, -.01)}, index=frame.index)
    benchmarks.iloc[0, 0] = -1.01
    with pytest.raises(ValueError, match="capitalizable"):
        fb._comparison(frame, benchmarks)


def test_shuffled_inputs_keep_spy_and_factors_aligned_and_universe_optional():
    frame = sample()
    assert fb.analyze(frame) == fb.analyze(frame.sample(frac=1, random_state=2))
    result = fb.analyze(frame.drop(columns="universo_ew"))
    assert "universe_ew" not in result["in_sample"]["metrics"]


def test_monthly_factors_align_with_real_spy_windows_not_french_market_proxy():
    frame = sample()
    rng = np.random.default_rng(23)
    monthly = pd.DataFrame(rng.normal(.002, .01, (108, 7)), columns=[*af.DEFAULT_FACTOR_COLS, "RF"],
                           index=pd.date_range("2016-07-01", periods=108, freq="MS"))
    periods = frame[["fecha", "hasta", "retorno", "spy", "universo_ew"]].sample(frac=1, random_state=2)
    aligned = fb.aligned_inputs(periods, monthly)
    np.testing.assert_allclose(aligned.spy, frame.spy)
    np.testing.assert_allclose(aligned["SPY-RF"], aligned.spy - aligned.RF)
    assert not np.allclose(aligned["SPY-RF"], aligned["Mkt-RF"])


def test_audit_reproducible_and_tampered_curves_rejected(tmp_path):
    path = tmp_path / "source.csv"
    sample().to_csv(path, index=False)
    directory = tmp_path / "audit"
    audit = fb.write_audit(path, directory)
    assert fb.load_audit(directory) == audit
    assert fb.write_audit(directory / "inputs.csv", directory) == audit
    curve_path = directory / "expanding-curves.csv"
    curve_path.write_bytes(curve_path.read_bytes() + b"modified\n")
    with pytest.raises(ValueError, match="artefacto"):
        fb.load_audit(directory)


def test_frozen_results_preserve_hac_inputs_and_reproduce_all_curves():
    docs = Path(__file__).resolve().parents[1] / "docs"
    original = pd.read_csv(docs / "academic-factors-hac-inputs.csv")
    inputs = pd.read_csv(docs / "factor-benchmark" / "inputs.csv")
    np.testing.assert_allclose(inputs[original.columns[2:]], original[original.columns[2:]], rtol=1e-12, atol=1e-14)
    audit = fb.load_audit(docs / "factor-benchmark")
    repeated = fb.analyze(inputs)
    for protocol in ("in_sample", "expanding"):
        np.testing.assert_allclose(fb.curve_table(audit[protocol]), fb.curve_table(repeated[protocol]),
                                   rtol=1e-10, atol=1e-12)
    hac = json.loads((docs / "academic-factors-hac-audit.json").read_text(encoding="utf-8"))
    assert audit["in_sample"]["regressions"]["ff6"]["coef"] == pytest.approx(hac["regression"]["coef"], abs=1e-12)
