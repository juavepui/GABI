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
