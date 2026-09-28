"""Statistical invariants: pairing, dependency, metric conventions and failed inputs."""

import json

import numpy as np
import pandas as pd
import pytest

from gabi import academic_factors, portfolio_metrics
from gabi import block_bootstrap as bb


def _returns(n=100):
    values = np.random.default_rng(7).normal(.002, .02, n)
    return pd.DataFrame({"strategy": values, "benchmark": values * .7}, index=pd.RangeIndex(n))


def test_pairing_identical_benchmark_produces_exact_zero_differences():
    frame = _returns()
    frame["benchmark"] = frame.strategy
    result, draws = bb.analyze_returns(frame, periods_per_year=4, block_size=4, strategy="strategy", n_boot=256)
    for metric in bb.COMPARISON_METRICS:
        assert (draws[f"vs_benchmark/{metric}"] == 0).all()
        summary = result["comparisons"]["benchmark"]["metrics"][metric]
        assert summary["observed"] == summary["lower"] == summary["upper"] == 0
        assert result["comparisons"]["benchmark"]["positive_fractions"][metric]["fraction"] == 0


def test_blocks_preserve_adjacency_and_wraparound_without_changing_length():
    indices = bb.circular_indices(37, 4, 200, np.random.default_rng(19))
    assert indices.shape == (200, 37)
    full_blocks = indices[:, :36].reshape(200, 9, 4)
    assert (np.diff(full_blocks, axis=2) % 37 == 1).all()
    assert ((full_blocks[:, :, 0] >= 34) & (full_blocks[:, :, -1] <= 2)).any()


def test_observed_metrics_include_initial_drawdown_and_match_existing_es():
    values = np.tile([-.2, .1, -.04, .09], 10)
    frame = pd.DataFrame({"strategy": values})
    result, _ = bb.analyze_returns(frame, periods_per_year=4, block_size=4, n_boot=128)
    metrics = result["series"]["strategy"]["metrics"]
    nav = np.r_[1., np.cumprod(1 + values)]
    assert metrics["cagr"]["observed"] == pytest.approx(nav[-1] ** (4 / len(values)) - 1)
    assert metrics["max_drawdown"]["observed"] == pytest.approx(np.min(nav / np.maximum.accumulate(nav) - 1))
    assert metrics["volatility"]["observed"] == pytest.approx(values.std(ddof=1) * 2)
    assert metrics["sharpe"]["observed"] == pytest.approx(values.mean() / values.std(ddof=1) * 2)
    assert metrics["es5"]["observed"] == pytest.approx(portfolio_metrics.expected_shortfall(pd.Series(values)))


def test_fractional_tail_mass_matches_existing_definition():
    values = np.linspace(-.13, .2, 57)
    result, _ = bb.analyze_returns(pd.DataFrame({"returns": values}), periods_per_year=4, block_size=4, n_boot=128)
    assert result["series"]["returns"]["metrics"]["es5"]["observed"] == pytest.approx(
        portfolio_metrics.expected_shortfall(pd.Series(values)))
    assert result["series"]["returns"]["tail_sparse"]


def test_constant_series_keeps_undefined_sharpes_and_exports_strict_json():
    result, draws = bb.analyze_returns(pd.DataFrame({"returns": np.full(50, .01)}), periods_per_year=4, block_size=4, n_boot=128)
    sharpe = result["series"]["returns"]["metrics"]["sharpe"]
    assert sharpe["observed"] is None
    assert sharpe["valid_draws"] == 0 and sharpe["undefined_draws"] == 128
    assert draws["returns/sharpe"].isna().all()
    assert draws["returns/cagr"].notna().all()
    json.dumps(result, allow_nan=False)


def test_total_loss_is_preserved_instead_of_dropping_the_path():
    frame = pd.DataFrame({"returns": np.r_[-1., np.full(39, .01)]})
    result, _ = bb.analyze_returns(frame, periods_per_year=4, block_size=4, n_boot=128)
    assert result["series"]["returns"]["metrics"]["cagr"]["observed"] == -1
    assert result["series"]["returns"]["metrics"]["max_drawdown"]["observed"] == -1


def test_seed_reproduces_full_distributions_and_observed_is_not_bootstrap_mean():
    frame = _returns()
    first, draws1 = bb.analyze_returns(frame, periods_per_year=4, block_size=4, strategy="strategy", n_boot=256)
    second, draws2 = bb.analyze_returns(frame, periods_per_year=4, block_size=4, strategy="strategy", n_boot=256)
    assert first == second
    pd.testing.assert_frame_equal(draws1, draws2)
    third, draws3 = bb.analyze_returns(frame, periods_per_year=4, block_size=4, strategy="strategy", n_boot=256, seed=8)
    assert not draws1.equals(draws3)
    assert first["input_sha256"] == third["input_sha256"]
    metric = first["series"]["strategy"]["metrics"]["cagr"]
    assert metric["observed"] != metric["bootstrap_mean"]
    changed = frame.copy()
    changed.iloc[0, 0] += .001
    audit, _ = bb.analyze_returns(changed, periods_per_year=4, block_size=4, n_boot=128)
    assert audit["input_sha256"] != first["input_sha256"]


@pytest.mark.parametrize("rho", [0., .8])
def test_mean_bootstrap_on_iid_and_autocorrelated_synthetic_series(rho):
    rng = np.random.default_rng(123)
    noise = rng.normal(0, .02, 1400)
    ar = np.zeros(1400)
    for i in range(1, len(ar)):
        ar[i] = rho * ar[i - 1] + noise[i]
    values = ar[400:]
    frame = pd.DataFrame({"ic": values, "spread": values * 2})
    audit, draws = bb.analyze_means(frame, periods_per_year=4, block_size=20, n_boot=4096)
    iid_means = values[bb.circular_indices(len(values), 1, 4096, np.random.default_rng(500050))].mean(axis=1)
    ratio = draws.ic.std() / iid_means.std()
    assert ratio > 2 if rho else .7 < ratio < 1.4
    np.testing.assert_allclose(draws.spread, draws.ic * 2, atol=1e-15)
    assert audit["means"]["ic"]["hac"]["se"] > 0


def test_mean_hac_comparison_reuses_existing_engine_and_checks_zero_disagreement():
    frame = _returns()
    result, _ = bb.analyze_returns(frame, periods_per_year=4, block_size=4, strategy="strategy", n_boot=256)
    excess = (frame.strategy - frame.benchmark).to_numpy()
    fit = academic_factors._ols(excess, np.ones((len(excess), 1)), ["mean"])
    hac = result["comparisons"]["benchmark"]["hac"]
    assert hac["se"] == fit["se"]["mean"]
    assert hac["hac_lags"] == fit["hac_lags"]
    assert hac["zero_conclusion_differs"] == (hac["bootstrap_excludes_zero"] != hac["hac_excludes_zero"])


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf, -1.01])
def test_rejects_missing_nonfinite_and_impossible_returns(bad):
    frame = _returns()
    frame.iloc[4, 1] = bad
    with pytest.raises(ValueError):
        bb.analyze_returns(frame, periods_per_year=4, block_size=4, n_boot=128)


@pytest.mark.parametrize("kwargs", [{"periods_per_year": None}, {"periods_per_year": True},
                                   {"block_size": 1}, {"block_size": 51}, {"block_size": 2.5},
                                   {"n_boot": 2}, {"ci": 1}, {"seed": None}])
def test_rejects_invalid_configuration(kwargs):
    settings = {"periods_per_year": 4, "block_size": 4, "n_boot": 128, **kwargs}
    with pytest.raises(ValueError):
        bb.analyze_returns(_returns(), **settings)


def test_rejects_quarterly_gaps_duplicates_unsorted_dates_and_daily_missing_session():
    frame = _returns(40)
    frame.index = pd.date_range("2010-01-01", periods=40, freq="QS")
    for bad in [frame.iloc[::-1], frame.drop(frame.index[5]), pd.concat([frame, frame.tail(1)])]:
        with pytest.raises(ValueError):
            bb.analyze_returns(bad, periods_per_year=4, block_size=4, n_boot=128)
    import exchange_calendars as xcals
    sessions = xcals.get_calendar("XNYS").sessions_in_range("2024-01-01", "2024-04-01").tz_localize(None)
    daily = _returns(len(sessions))
    daily.index = sessions
    audit, _ = bb.analyze_returns(daily, periods_per_year=252, block_size=10, n_boot=128)
    assert audit["n_obs"] == len(sessions)
    with pytest.raises(ValueError, match="sesiones"):
        bb.analyze_returns(daily.drop(daily.index[4]), periods_per_year=252, block_size=10, n_boot=128)


def test_sensitivity_keeps_every_fixed_length_and_distributions():
    audit, draws = bb.analyze_sensitivity(_returns(), periods_per_year=4, strategy="strategy", n_boot=128)
    assert audit["primary_block"] == 4
    assert list(audit["runs"]) == ["4", "2", "8"]
    assert draws.groupby("block_size").size().to_dict() == {2: 128, 4: 128, 8: 128}
    assert set(bb.interval_table(audit).block_size) == {2, 4, 8}


def test_saved_load_detects_changed_distribution(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "OUTPUT", tmp_path)
    path = tmp_path / "some-distributions.csv"
    path.write_text("x\n1\n")
    (tmp_path / "resultado.json").write_text(json.dumps({"artifacts_sha256": {path.name: bb._hash(path)}}))
    bb.load_saved()
    path.write_text("x\n2\n")
    with pytest.raises(ValueError, match="ha cambiado"):
        bb.load_saved()
