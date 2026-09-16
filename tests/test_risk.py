import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import risk


def _price_df(prices):
    dates = pd.date_range("2023-01-02", periods=len(prices), freq="B")
    return pd.DataFrame({"close": prices}, index=dates)


def test_empty_price_df_returns_empty_result():
    result = risk.compute_risk_metrics(pd.DataFrame())
    assert result == risk.EMPTY_RESULT


def test_smooth_uptrend_has_low_volatility_and_no_drawdown():
    n = 500
    prices = np.linspace(100, 200, n)  # sube en línea recta, sin retrocesos
    df = _price_df(prices)
    result = risk.compute_risk_metrics(df)

    assert result["volatility"] is not None
    assert result["volatility"] < 0.05  # prácticamente sin ruido día a día
    assert result["max_drawdown"] == 0.0  # nunca baja del máximo previo
    assert result["sharpe_ratio"] > 0
    assert result["win_rate_monthly"] == 1.0  # todos los meses suben


def test_volatile_series_has_higher_volatility_than_smooth_series():
    n = 500
    smooth = np.linspace(100, 150, n)
    rng = np.random.default_rng(42)
    noisy = 100 + np.cumsum(rng.normal(0.1, 3.0, n))
    smooth_df, noisy_df = _price_df(smooth), _price_df(noisy)

    smooth_result = risk.compute_risk_metrics(smooth_df)
    noisy_result = risk.compute_risk_metrics(noisy_df)
    assert noisy_result["volatility"] > smooth_result["volatility"]


def test_max_drawdown_detects_known_crash():
    # Sube a 200, cae a 100 (-50%), luego recupera un poco.
    up = np.linspace(100, 200, 100)
    down = np.linspace(200, 100, 50)
    recover = np.linspace(100, 140, 50)
    prices = np.concatenate([up, down, recover])
    df = _price_df(prices)
    result = risk.compute_risk_metrics(df)
    assert round(result["max_drawdown"], 2) == -0.50


def test_beta_of_stock_identical_to_benchmark_is_one():
    n = 300
    rng = np.random.default_rng(7)
    bench_prices = 100 + np.cumsum(rng.normal(0.05, 1.0, n))
    bench_df = _price_df(bench_prices)
    stock_df = _price_df(bench_prices.copy())  # misma serie exacta -> beta = 1

    result = risk.compute_risk_metrics(stock_df, benchmark_df=bench_df)
    assert result["beta_calc"] is not None
    assert round(result["beta_calc"], 2) == 1.0
    assert round(result["alpha"], 3) == 0.0  # sin diferencia de retorno -> alpha ~0


def test_double_leveraged_stock_has_beta_near_two():
    n = 300
    rng = np.random.default_rng(7)
    bench_returns = rng.normal(0.0003, 0.01, n)
    bench_prices = 100 * np.cumprod(1 + bench_returns)
    stock_prices = 100 * np.cumprod(1 + 2 * bench_returns)  # 2x apalancado
    bench_df, stock_df = _price_df(bench_prices), _price_df(stock_prices)

    result = risk.compute_risk_metrics(stock_df, benchmark_df=bench_df)
    assert 1.8 <= result["beta_calc"] <= 2.2


def test_downtrend_gives_negative_sharpe_and_low_win_rate():
    n = 400
    prices = np.linspace(200, 100, n)
    df = _price_df(prices)
    result = risk.compute_risk_metrics(df)
    assert result["sharpe_ratio"] < 0
    assert result["win_rate_monthly"] < 0.5


def test_no_downside_days_means_sortino_is_none():
    n = 300
    prices = np.linspace(100, 200, n)  # estrictamente creciente, sin días negativos
    df = _price_df(prices)
    result = risk.compute_risk_metrics(df)
    assert result["sortino_ratio"] is None  # sin desviación a la baja que dividir


def test_custom_risk_free_rate_changes_sharpe():
    n = 400
    rng = np.random.default_rng(3)
    prices = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n))
    df = _price_df(prices)
    low_rf = risk.compute_risk_metrics(df, risk_free_rate=0.0)
    high_rf = risk.compute_risk_metrics(df, risk_free_rate=0.20)
    assert low_rf["sharpe_ratio"] > high_rf["sharpe_ratio"]
