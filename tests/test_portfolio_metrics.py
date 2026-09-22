import numpy as np
import pandas as pd
import pytest

from gabi import portfolio_metrics as pm


def test_calmar_ratio_divides_cagr_by_absolute_drawdown():
    assert pm.calmar_ratio(0.20, -0.10) == pytest.approx(2.0)


def test_calmar_ratio_none_when_inputs_missing_or_no_drawdown():
    assert pm.calmar_ratio(None, -0.10) is None
    assert pm.calmar_ratio(0.20, None) is None
    assert pm.calmar_ratio(0.20, 0.0) is None


def test_recovery_time_counts_days_from_prior_peak_to_new_high():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    curve = pd.Series([100.0, 110.0, 90.0, 95.0, 105.0, 115.0], index=dates)
    # pico previo a la caida maxima: dia 1 (110). recupera >=110 en el dia 5.
    assert pm.recovery_time(curve) == 4


def test_recovery_time_none_when_never_recovers():
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    curve = pd.Series([100.0, 110.0, 90.0, 95.0], index=dates)
    assert pm.recovery_time(curve) is None


def test_recovery_time_none_when_no_drawdown_at_all():
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    curve = pd.Series([100.0, 105.0, 110.0, 120.0], index=dates)
    assert pm.recovery_time(curve) is None


def test_beta_vs_benchmark_recovers_exact_linear_slope():
    dates = pd.date_range("2024-01-01", periods=40, freq="D")
    rng = np.linspace(-0.01, 0.01, 40)
    bench = pd.Series(rng, index=dates)
    strategy = pd.Series(rng * 1.5, index=dates)  # sin ruido: beta exacto 1.5
    assert pm.beta_vs_benchmark(strategy, bench) == pytest.approx(1.5, rel=1e-6)


def test_beta_vs_benchmark_none_with_too_few_observations():
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    s = pd.Series(np.linspace(-0.01, 0.01, 10), index=dates)
    assert pm.beta_vs_benchmark(s, s) is None


def test_tracking_error_and_information_ratio_match_manual_formula():
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    rng = np.random.RandomState(0)
    bench = pd.Series(rng.normal(0.0005, 0.01, 50), index=dates)
    strategy = bench + pd.Series(rng.normal(0.0002, 0.003, 50), index=dates)
    diff = strategy - bench
    expected_te = diff.std(ddof=1) * np.sqrt(pm.TRADING_DAYS_PER_YEAR)
    expected_ir = (diff.mean() * pm.TRADING_DAYS_PER_YEAR) / expected_te

    assert pm.tracking_error(strategy, bench) == pytest.approx(expected_te)
    assert pm.information_ratio(strategy, bench) == pytest.approx(expected_ir)


def test_information_ratio_none_when_tracking_error_is_zero():
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    bench = pd.Series([0.002] * 10, index=dates)
    strategy = pd.Series([0.003] * 10, index=dates)  # diferencia constante -> std exacto 0
    assert pm.information_ratio(strategy, bench) is None


def test_capture_ratios_identifies_up_and_down_months():
    dates = pd.date_range("2024-01-01", periods=4, freq="ME")
    # meses: benchmark sube, sube, baja, baja. Estrategia se mueve el doble en ambos casos.
    bench = pd.Series([0.10, 0.05, -0.10, -0.05], index=dates)
    strategy = pd.Series([0.20, 0.10, -0.20, -0.10], index=dates)
    result = pm.capture_ratios(strategy, bench)
    assert result["upside"] == pytest.approx(2.0)
    assert result["downside"] == pytest.approx(2.0)


def test_rolling_sharpe_returns_empty_series_when_shorter_than_window():
    returns = pd.Series(np.linspace(-0.01, 0.01, 10),
                        index=pd.date_range("2024-01-01", periods=10, freq="D"))
    assert pm.rolling_sharpe(returns, window=252).empty


def test_rolling_sharpe_produces_expected_length_and_matches_manual_value():
    dates = pd.date_range("2024-01-01", periods=300, freq="D")
    rng = np.random.RandomState(1)
    returns = pd.Series(rng.normal(0.0006, 0.01, 300), index=dates)
    window = 252
    result = pm.rolling_sharpe(returns, window=window, risk_free_rate=0.04)
    assert len(result) == 300 - window + 1

    daily_rf = (1 + 0.04) ** (1 / 252) - 1
    window_slice = returns.iloc[:window]
    expected_first = ((window_slice - daily_rf).mean() * 252) / (window_slice.std(ddof=1) * np.sqrt(252))
    assert result.iloc[0] == pytest.approx(expected_first)


def test_historical_var_inverse_ecdf_and_exact_tail_for_100_observations():
    # Pérdidas -49%..50%: VaR95=45%, ES95=media(46%,...,50%)=48%.
    returns = pd.Series(-np.arange(-49, 51) / 100)
    assert pm.historical_var(returns, .95) == pytest.approx(.45)
    assert pm.expected_shortfall(returns, .95) == pytest.approx(.48)
    assert pm.historical_var(returns, .99) == pytest.approx(.49)
    assert pm.expected_shortfall(returns, .99) == pytest.approx(.50)
    assert pm.historical_tail_risk(returns)["tail_observations"] == 5


def test_fractional_tail_does_not_average_all_points_beyond_interpolated_quantile():
    returns = pd.Series([-0.20, -0.10, *([0.] * 28)])
    # 1.5 observaciones: la peor entera y media de la segunda, no su media simple.
    result = pm.historical_tail_risk(returns, .95)
    assert result["var"] == pytest.approx(.10)
    assert result["expected_shortfall"] == pytest.approx((.20 + .5 * .10) / 1.5)
    assert result["tail_mass"] == pytest.approx(1.5)
    assert result["tail_observations"] == 2
    assert result["status"] == "sparse"


def test_ties_at_var_receive_only_required_mass():
    returns = pd.Series([-.20, *([-.10] * 19)])
    # A 90%, cola de 2 observaciones; contar todos los >=VaR daría .105, no .15.
    assert pm.historical_var(returns, .9) == pytest.approx(.10)
    assert pm.expected_shortfall(returns, .9) == pytest.approx(.15)


def test_36_quarters_warn_99_percent_is_just_the_worst_observation():
    returns = pd.Series([-.30, -.15, *([.02] * 34)])
    summary = pm.tail_risk_metrics(returns, horizon="un trimestre")
    assert summary["95"]["tail_mass"] == pytest.approx(1.8)
    assert summary["95"]["expected_shortfall"] == pytest.approx((.30 + .8 * .15) / 1.8)
    assert summary["99"]["tail_mass"] == pytest.approx(.36)
    assert summary["99"]["status"] == "below_resolution"
    assert summary["99"]["var"] == summary["99"]["expected_shortfall"] == pytest.approx(.30)
    assert summary["horizon"] == "un trimestre"
    assert summary["annualized"] is False


@pytest.mark.parametrize("confidence", [.01, .5, .90, .95, .99, .999])
def test_es_matches_independent_rockafellar_uryasev_minimization(confidence):
    returns = pd.Series([-.3, -.1, -.1, 0, .05, .07, .07, .1, .2])
    losses = -returns.to_numpy()
    # Min_z [z + E(max(L-z, 0))/(1-alpha)], minimizador entre pérdidas observadas.
    expected = min(z + np.maximum(losses - z, 0).mean() / (1 - confidence) for z in losses)
    assert pm.expected_shortfall(returns, confidence) == pytest.approx(expected, abs=1e-12)
    assert pm.expected_shortfall(returns, confidence) >= pm.historical_var(returns, confidence) - 1e-12


def test_tail_risk_translation_scaling_permutation_and_confidence_monotonicity():
    rng = np.random.default_rng(11)
    returns = pd.Series(rng.standard_t(4, size=1001) * .02)
    for metric in (pm.historical_var, pm.expected_shortfall):
        baseline = metric(returns)
        assert metric(returns.sample(frac=1, random_state=3)) == pytest.approx(baseline)
        assert metric(returns + .01) == pytest.approx(baseline - .01)
        assert metric(3 * returns) == pytest.approx(3 * baseline)
        assert metric(returns, .99) >= metric(returns, .95)


@pytest.mark.parametrize("confidence", [0, 1, -.1, 1.1, np.nan, np.inf, True, None, [.95], "invalid"])
def test_tail_invalid_confidence(confidence):
    with pytest.raises(ValueError, match="confidence"):
        pm.historical_tail_risk(pd.Series([.01, -.01]), confidence)


@pytest.mark.parametrize("values", [[.1, np.nan], [.1, np.inf], [-np.inf], [[.1], [.2]]])
def test_tail_and_moments_reject_nonfinite_or_multidimensional_inputs(values):
    for function in (pm.historical_tail_risk, pm.return_distribution, pm.tail_risk_metrics):
        with pytest.raises(ValueError, match="unidimensional"):
            function(np.array(values))


def test_empty_small_and_constant_samples_have_explicit_undefined_moments():
    empty = pm.tail_risk_metrics(pd.Series(dtype=float))
    assert empty["95"]["var"] is None and empty["99"]["expected_shortfall"] is None
    assert empty["95"]["status"] == "empty"
    assert empty["skewness"] is None and empty["excess_kurtosis"] is None
    for n in (1, 2, 3, 4, 100):
        summary = pm.tail_risk_metrics(pd.Series([.01] * n))
        assert summary["95"]["var"] == pytest.approx(-.01)  # Ganancia, sin recortar a cero.
        assert summary["95"]["expected_shortfall"] == pytest.approx(-.01)
        assert summary["skewness"] is None and summary["excess_kurtosis"] is None
    assert pm.return_distribution(pd.Series([-.01, .01]))["skewness"] is None
    triple = pm.return_distribution(pd.Series([-.01, 0, .01]))
    assert triple["skewness"] == pytest.approx(0)
    assert triple["excess_kurtosis"] is None


def test_distribution_matches_independent_scipy_bias_corrected_estimators():
    from scipy.stats import kurtosis, skew

    rng = np.random.default_rng(313)
    for n in (4, 36, 1000):
        returns = pd.Series(rng.standard_t(5, size=n) * .02)
        result = pm.return_distribution(returns)
        assert result["skewness"] == pytest.approx(skew(returns, bias=False), abs=1e-12)
        assert result["excess_kurtosis"] == pytest.approx(kurtosis(returns, fisher=True, bias=False), abs=1e-12)
        assert pm.return_distribution(-returns)["skewness"] == pytest.approx(-result["skewness"])
        assert pm.return_distribution(returns * 100)["excess_kurtosis"] == pytest.approx(result["excess_kurtosis"])


def test_nav_returns_do_not_add_initial_zero_and_allow_total_terminal_loss():
    nav = pd.Series([100., 110., 88., 0.], index=pd.date_range("2020-01-01", periods=4))
    np.testing.assert_allclose(pm.returns_from_nav(nav), [.1, -.2, -1])
    assert pm.returns_from_nav(nav.iloc[:1]).empty
    assert pm.returns_from_nav(nav.iloc[:0]).empty


@pytest.mark.parametrize("problem", ["nan", "inf", "zero_divisor", "negative", "duplicate", "unordered", "nat"])
def test_nav_returns_reject_missing_data_instead_of_filling_or_dropping(problem):
    nav = pd.Series([100., 110., 105.], index=pd.date_range("2020-01-01", periods=3))
    if problem in ("nan", "inf", "zero_divisor", "negative"):
        nav.iloc[1] = {"nan": np.nan, "inf": np.inf, "zero_divisor": 0, "negative": -1}[problem]
    elif problem == "duplicate":
        nav.index = [nav.index[0], nav.index[0], nav.index[2]]
    elif problem == "unordered":
        nav = nav.iloc[::-1]
    else:
        nav.index = [nav.index[0], pd.NaT, nav.index[2]]
    with pytest.raises(ValueError):
        pm.returns_from_nav(nav)


def test_published_tail_audit_matches_all_24_saved_trial_series():
    import hashlib
    import json
    from pathlib import Path

    docs = Path(__file__).resolve().parents[1] / "docs"
    audit = json.loads((docs / "tail-risk-audit.json").read_text(encoding="utf-8"))
    source = docs / audit["source"]
    assert hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == audit["source_sha256"]
    matrix = pd.read_csv(source, index_col=0)
    assert audit["n_trials"] == len(matrix.columns) == 24
    for name in matrix:
        expected = pm.tail_risk_metrics(matrix[name], horizon="un trimestre")
        saved = audit["summaries"][name]
        assert saved["n_obs"] == 36
        assert saved["skewness"] == pytest.approx(expected["skewness"], abs=1e-12)
        assert saved["excess_kurtosis"] == pytest.approx(expected["excess_kurtosis"], abs=1e-12)
        for level in ("95", "99"):
            assert saved[level]["var"] == pytest.approx(expected[level]["var"], abs=1e-12)
            assert saved[level]["expected_shortfall"] == pytest.approx(expected[level]["expected_shortfall"], abs=1e-12)
        assert saved["99"]["status"] == "below_resolution"
