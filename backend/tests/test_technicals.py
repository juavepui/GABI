import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import technicals


def _price_df(prices, adj_close=None):
    dates = pd.date_range("2022-01-03", periods=len(prices), freq="B")
    data = {"close": prices}
    if adj_close is not None:
        data["adj_close"] = adj_close
    return pd.DataFrame(data, index=dates)


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


def test_momentum_uses_adj_close_not_nominal_close():
    # 'close' plano (sin tendencia): si momentum mirase esta columna, daría
    # ~0. 'adj_close' con tendencia alcista simula lo que pasaría de verdad
    # tras repartir dividendos -- el precio en pantalla ('close') no sube,
    # pero el retorno real para quien mantuvo la posición sí.
    n = 400
    close = np.full(n, 100.0)
    adj_close = np.linspace(70, 100, n)
    df = _price_df(close, adj_close=adj_close)
    result = technicals.compute_technicals(df)

    assert result["price"] == 100.0  # nominal, no ajustado -- lo que se ve en pantalla
    assert result["momentum_6m"] > 0
    assert result["momentum_12m"] > 0


def test_falls_back_to_close_when_adj_close_incomplete():
    # Caché antiguo: algunas filas sin adj_close -- todo o nada, cae a close
    # entero en vez de mezclar ajustado y sin ajustar en la misma serie.
    n = 400
    close = np.linspace(50, 150, n)
    adj_close = np.concatenate([[np.nan] * 10, np.linspace(70, 150, n - 10)])
    df = _price_df(close, adj_close=adj_close)
    result = technicals.compute_technicals(df)

    assert result["price"] == close[-1]
    assert result["momentum_12m"] == pytest.approx(close[-1] / close[-1 - 252] - 1)


# --- #31: price-based metrics on historical (2010-2015) series --------------

def test_twelve_month_momentum_needs_252_returns_and_sma200_needs_200_sessions():
    short = technicals.compute_technicals(_price_df(np.linspace(100, 150, 252)))
    assert short["momentum_12m"] is None  # 252 closes = 251 returns
    assert technicals.compute_technicals(_price_df(np.linspace(100, 150, 253)))["momentum_12m"] is not None
    assert technicals.compute_technicals(_price_df(np.linspace(100, 150, 199)))["price_vs_sma200"] is None
    assert technicals.compute_technicals(_price_df(np.linspace(100, 150, 200)))["price_vs_sma200"] is not None


def test_relative_strength_is_missing_when_the_benchmark_has_a_gap():
    n = 300
    stock = _price_df(np.linspace(100, 200, n))
    bench = _price_df(np.linspace(100, 120, n)).drop(pd.bdate_range("2022-01-03", periods=n)[-50])
    result = technicals.compute_technicals(stock, benchmark_df=bench)
    assert result["momentum_6m"] is not None
    assert result["rel_strength_6m"] is None  # windows would cover different dates


def test_split_inside_the_window_does_not_move_adjusted_momentum_or_sma():
    adjusted = np.linspace(100, 130, 300)
    nominal = adjusted.copy()
    nominal[150:] = nominal[150:] / 2  # 2:1 split: only the nominal close halves
    result = technicals.compute_technicals(_price_df(nominal, adj_close=adjusted))
    assert result["momentum_12m"] == pytest.approx(adjusted[-1] / adjusted[-253] - 1)
    assert result["price_vs_sma200"] > 0  # would be deeply negative on nominal closes
    assert result["price"] == pytest.approx(nominal[-1])  # displayed price stays nominal


def test_metrics_only_see_observations_up_to_the_ranking_date(monkeypatch):
    from gabi import risk, screener_asof, storage
    dates = pd.bdate_range("2012-01-02", periods=400)
    values = np.linspace(100, 200, 400)
    values[350:] = 50  # a crash after the ranking date
    frame = pd.DataFrame({"close": values, "adj_close": values}, index=dates)
    monkeypatch.setattr(storage, "get_prices", lambda symbol: frame)
    as_of = dates[300]
    seen = screener_asof._price_history_as_of("AAA", as_of)
    assert seen.index.max() == as_of
    assert risk.compute_risk_metrics(seen)["max_drawdown"] == 0.0
    assert risk.compute_risk_metrics(frame)["max_drawdown"] < -0.5  # the future crash is not visible
    assert technicals.compute_technicals(seen)["momentum_12m"] > 0
