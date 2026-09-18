import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import multifactor_backtest as bt, stats_rigor as sr


# --- probabilistic_sharpe_ratio ---

def test_psr_normal_case_matches_sharpe_standard_error_cross_check():
    """Con skew=0/kurtosis=3 (retornos normales), PSR debe coincidir
    aproximadamente con la aproximacion normal que ya usa
    sharpe_standard_error -- comprobacion cruzada entre los dos modulos."""
    sharpe, n = 0.71, 9.0
    se = bt.sharpe_standard_error(sharpe, n)
    psr = sr.probabilistic_sharpe_ratio(sharpe, n, benchmark_sharpe=sharpe - 2 * se)
    assert psr == pytest.approx(norm.cdf(2), abs=0.015)


def test_psr_returns_half_when_sharpe_equals_benchmark():
    assert sr.probabilistic_sharpe_ratio(0.5, 36, benchmark_sharpe=0.5) == pytest.approx(0.5)


def test_psr_increases_with_more_observations():
    low_n = sr.probabilistic_sharpe_ratio(0.5, 10, benchmark_sharpe=0.0)
    high_n = sr.probabilistic_sharpe_ratio(0.5, 200, benchmark_sharpe=0.0)
    assert high_n > low_n


def test_psr_rejects_n_leq_1():
    with pytest.raises(ValueError):
        sr.probabilistic_sharpe_ratio(0.5, 1)


def test_psr_annualized_matches_manual_conversion():
    annualized_sharpe, n, ppy = 0.83, 36, 4.0
    expected = sr.probabilistic_sharpe_ratio(annualized_sharpe / np.sqrt(ppy), n,
                                             benchmark_sharpe=0.0)
    actual = sr.probabilistic_sharpe_ratio_annualized(annualized_sharpe, n, ppy, benchmark_sharpe=0.0)
    assert actual == pytest.approx(expected)


def test_psr_from_returns_matches_manual_moments():
    rng = np.random.RandomState(0)
    returns = pd.Series(rng.normal(0.0008, 0.01, 252))
    result = sr.probabilistic_sharpe_ratio_from_returns(returns, periods_per_year=252)
    assert result["n"] == 252
    assert result["skew"] == pytest.approx(float(pd.Series(returns).skew()), rel=0.2)
    # kurtosis no-excedente de una normal generada debe rondar 3
    assert result["kurtosis"] == pytest.approx(3.0, abs=1.0)
    assert 0.0 <= result["psr"] <= 1.0


# --- expected_max_sharpe / deflated_sharpe_ratio ---

def test_expected_max_sharpe_requires_at_least_two_trials():
    with pytest.raises(ValueError):
        sr.expected_max_sharpe([0.5])


def test_expected_max_sharpe_zero_variance_returns_the_common_value():
    assert sr.expected_max_sharpe([0.5, 0.5, 0.5]) == pytest.approx(0.5)


def test_expected_max_sharpe_grows_with_more_trials_same_variance():
    trials_small = [0.1, 0.3, 0.5, 0.7, 0.9]
    trials_large = trials_small * 4  # misma varianza, mas intentos (N)
    small = sr.expected_max_sharpe(trials_small)
    large = sr.expected_max_sharpe(trials_large)
    assert large > small  # mas intentos -> el maximo esperado por azar sube


def test_deflated_sharpe_ratio_real_position_count_family():
    """Caso real de esta sesion: familia top-10/20/30 + filtro SMA200 +
    semestral/anual (Sharpe anualizados ya documentados en el README,
    universo/muestreo corregido). El Sharpe deflactado del top-20 (0.71)
    debe ser menor que su PSR sin deflactar (frente a benchmark 0)."""
    trial_sharpes = [0.74, 0.71, 0.51, 0.60, 0.68, 0.61]  # top10/20/30/filtro/semestral/anual
    result = sr.deflated_sharpe_ratio(selected_sharpe=0.71, trial_sharpes=trial_sharpes,
                                      n_obs=36, periods_per_year=4)
    raw_psr = sr.probabilistic_sharpe_ratio_annualized(0.71, 36, 4, benchmark_sharpe=0.0)
    assert result["dsr"] < raw_psr
    assert result["n_trials"] == 6
    assert result["sr0_benchmark"] > 0


# --- bootstrap_sharpe_ci ---

def test_bootstrap_ci_requires_minimum_observations():
    with pytest.raises(ValueError):
        sr.bootstrap_sharpe_ci(pd.Series(np.random.normal(0, 0.01, 10)), periods_per_year=252)


def test_bootstrap_ci_narrows_with_more_observations():
    rng = np.random.RandomState(1)
    short = pd.Series(rng.normal(0.0006, 0.01, 100))
    long = pd.Series(rng.normal(0.0006, 0.01, 1000))
    ci_short = sr.bootstrap_sharpe_ci(short, periods_per_year=252, n_boot=300, seed=1)
    ci_long = sr.bootstrap_sharpe_ci(long, periods_per_year=252, n_boot=300, seed=1)
    width_short = ci_short["upper"] - ci_short["lower"]
    width_long = ci_long["upper"] - ci_long["lower"]
    assert width_long < width_short


def test_bootstrap_ci_contains_point_estimate():
    rng = np.random.RandomState(2)
    returns = pd.Series(rng.normal(0.0005, 0.012, 500))
    result = sr.bootstrap_sharpe_ci(returns, periods_per_year=252, n_boot=500, seed=2)
    assert result["lower"] <= result["point_estimate"] <= result["upper"]


# --- pbo_cscv ---

def test_pbo_low_when_one_strategy_has_a_real_persistent_edge():
    rng = np.random.RandomState(3)
    n = 400
    winner = rng.normal(0.002, 0.01, n)  # ventaja real y consistente
    noise_b = rng.normal(0.0, 0.01, n)
    noise_c = rng.normal(0.0, 0.01, n)
    noise_d = rng.normal(0.0, 0.01, n)
    matrix = pd.DataFrame({"winner": winner, "b": noise_b, "c": noise_c, "d": noise_d})
    result = sr.pbo_cscv(matrix, n_splits=8)
    assert result["pbo"] < 0.2


def test_pbo_near_half_when_all_strategies_are_pure_noise():
    rng = np.random.RandomState(4)
    n = 400
    matrix = pd.DataFrame({f"s{i}": rng.normal(0.0, 0.01, n) for i in range(6)})
    result = sr.pbo_cscv(matrix, n_splits=8)
    assert 0.3 <= result["pbo"] <= 0.7


def test_pbo_rejects_odd_n_splits():
    matrix = pd.DataFrame({"a": np.random.normal(0, 0.01, 50), "b": np.random.normal(0, 0.01, 50)})
    with pytest.raises(ValueError):
        sr.pbo_cscv(matrix, n_splits=7)


def test_pbo_rejects_single_strategy():
    matrix = pd.DataFrame({"a": np.random.normal(0, 0.01, 50)})
    with pytest.raises(ValueError):
        sr.pbo_cscv(matrix, n_splits=8)
