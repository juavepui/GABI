import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import technicals


def _price_df(prices):
    dates = pd.date_range("2022-01-03", periods=len(prices), freq="B")
    return pd.DataFrame({"close": prices}, index=dates)


def test_empty_df_returns_empty_result():
    result = technicals.compute_technicals(pd.DataFrame())
    assert result["price"] is None
    assert result["rsi14"] is None


def test_rsi_flat_prices_are_neutral_and_short_history_is_unknown():
    assert technicals.compute_technicals(_price_df([100] * 30))["rsi14"] == 50
    assert technicals.compute_technicals(_price_df([100] * 5))["rsi14"] is None


def test_uptrend_gives_positive_momentum_and_high_rsi():
    n = 400
    prices = np.linspace(50, 150, n)  # tendencia alcista sostenida
    df = _price_df(prices)
    result = technicals.compute_technicals(df)

    assert result["price"] == prices[-1]
    assert result["momentum_6m"] > 0
    assert result["momentum_12m"] > 0
    assert result["rsi14"] > 50
    assert result["price_vs_sma50"] > 0
    assert result["price_vs_sma200"] > 0


def test_downtrend_gives_negative_momentum_and_low_rsi():
    n = 400
    prices = np.linspace(150, 50, n)
    df = _price_df(prices)
    result = technicals.compute_technicals(df)

    assert result["momentum_6m"] < 0
    assert result["rsi14"] < 50


def test_golden_cross_detected():
    # Caída larga (SMA50 por debajo de SMA200) seguida de una subida fuerte y
    # reciente que hace que SMA50 cruce por encima de SMA200 dentro de los
    # últimos 20 días.
    down = np.linspace(150, 80, 220)
    up = np.linspace(80, 200, 50)
    prices = np.concatenate([down, up])
    df = _price_df(prices)
    result = technicals.compute_technicals(df)
    assert result["golden_cross_recent"] is True


def test_relative_strength_uses_benchmark():
    n = 300
    stock = _price_df(np.linspace(100, 200, n))
    bench = _price_df(np.linspace(100, 120, n))
    result = technicals.compute_technicals(stock, benchmark_df=bench)
    assert result["rel_strength_6m"] is not None
    assert result["rel_strength_6m"] > 0
