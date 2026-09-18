import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, portfolio_lab as pl, portfolio_backtest as pb, storage


def _seed_prices(dates, symbol_closes):
    for symbol, closes in symbol_closes:
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * len(closes)}, index=dates))


def _history(closes: list, start="2022-01-03") -> pd.DataFrame:
    """DataFrame con la misma forma que devuelve storage.get_prices_multi."""
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes,
                         "volume": [1] * len(closes), "adj_close": closes}, index=idx)


def _synthetic_walk(n, daily_std, seed, start_price=100.0):
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, daily_std, n)
    return start_price * np.cumprod(1 + returns)


# --- _rebalance_to_weights (pesos NO equiponderados) ---

def test_rebalance_to_weights_hits_arbitrary_targets_and_conserves_value():
    shares = {"AAA": 10.0, "CCC": 4.0}
    entry_price = {"AAA": 100.0, "BBB": 50.0, "CCC": 25.0}
    before_value = shares["AAA"] * 100 + shares["CCC"] * 25
    target_weights = {"AAA": 0.6, "BBB": 0.3, "CCC": 0.1}
    result = pb._rebalance_to_weights(cash=0.0, shares=shares, target_weights=target_weights,
                                      entry_price=entry_price, commission_usd=1.0, spread_bps=0.0)
    after_value = result["cash"] + sum(shares[s] * entry_price[s] for s in shares)
    assert after_value == pytest.approx(before_value - result["comision_pagada"])
    # los targets se calculan sobre el valor de cartera ANTES de restar comisiones (cash=0 -> == before_value)
    for symbol, weight in target_weights.items():
        assert shares.get(symbol, 0.0) * entry_price[symbol] == pytest.approx(weight * before_value, rel=1e-6)


def test_rebalance_equal_weight_is_a_special_case_of_rebalance_to_weights():
    shares_a, shares_b = {"AAA": 10.0}, {"AAA": 10.0}
    entry_price = {"AAA": 150.0, "BBB": 50.0}
    result_a = pb._rebalance(cash=0.0, shares=shares_a, picks=["AAA", "BBB"], entry_price=entry_price,
                             top_n=2, commission_usd=1.0, spread_bps=0.0)
    result_b = pb._rebalance_to_weights(cash=0.0, shares=shares_b, target_weights={"AAA": 0.5, "BBB": 0.5},
                                        entry_price=entry_price, commission_usd=1.0, spread_bps=0.0)
    assert shares_a == pytest.approx(shares_b)
    assert result_a["comision_pagada"] == pytest.approx(result_b["comision_pagada"])


# --- Cada esquema de pesos suma ~1 y no da pesos negativos ---

def test_weights_equal_sums_to_one():
    weights = pl._weights_equal(["AAA", "BBB", "CCC"])
    assert sum(weights.values()) == pytest.approx(1.0)
    assert all(w >= 0 for w in weights.values())


def test_weights_inverse_vol_sums_to_one_and_nonnegative():
    histories = {"AAA": _history(list(_synthetic_walk(300, 0.005, seed=1))),
                "BBB": _history(list(_synthetic_walk(300, 0.03, seed=2)))}
    weights = pl._weights_inverse_vol(["AAA", "BBB"], histories)
    assert sum(weights.values()) == pytest.approx(1.0, rel=1e-6)
    assert all(w >= 0 for w in weights.values())


def test_weights_min_variance_sums_to_one_and_nonnegative():
    histories = {"AAA": _history(list(_synthetic_walk(300, 0.005, seed=1))),
                "BBB": _history(list(_synthetic_walk(300, 0.03, seed=2)))}
    weights = pl._weights_min_variance(["AAA", "BBB"], histories)
    assert sum(weights.values()) == pytest.approx(1.0, rel=1e-6)
    assert all(w >= 0 for w in weights.values())


def test_weights_score_sums_to_one_and_nonnegative():
    scores = pd.Series({"AAA": 80.0, "BBB": 20.0, "CCC": 0.0})
    weights = pl._weights_score(["AAA", "BBB", "CCC"], scores)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert all(w >= 0 for w in weights.values())
    assert weights["AAA"] > weights["BBB"] > weights["CCC"]  # respeta el orden del score


def test_weights_score_constrained_sums_to_one_and_respects_caps():
    histories = {s: _history(list(_synthetic_walk(300, 0.02, seed=i))) for i, s in enumerate(["AAA", "BBB", "CCC"])}
    scores = pd.Series({"AAA": 80.0, "BBB": 60.0, "CCC": 40.0})
    sector_by_symbol = {"AAA": "Tech", "BBB": "Health", "CCC": "Financials"}
    weights = pl._weights_score_constrained(["AAA", "BBB", "CCC"], scores, histories,
                                            position_cap=0.5, sector_cap=0.8, sector_by_symbol=sector_by_symbol)
    assert sum(weights.values()) == pytest.approx(1.0, rel=1e-6)
    assert all(w >= -1e-9 for w in weights.values())
    assert all(w <= 0.5 + 1e-6 for w in weights.values())


def test_weights_risk_parity_sums_to_one_and_nonnegative():
    histories = {"AAA": _history(list(_synthetic_walk(300, 0.005, seed=1))),
                "BBB": _history(list(_synthetic_walk(300, 0.03, seed=2)))}
    weights = pl._weights_risk_parity(["AAA", "BBB"], histories)
    assert sum(weights.values()) == pytest.approx(1.0, rel=1e-6)
    assert all(w >= 0 for w in weights.values())


# --- Casos de referencia: Min Variance vs Risk Parity NO son lo mismo ---

def test_min_variance_favors_the_lower_volatility_asset():
    histories = {"LOW": _history(list(_synthetic_walk(300, 0.003, seed=10))),
                "HIGH": _history(list(_synthetic_walk(300, 0.04, seed=11)))}
    weights = pl._weights_min_variance(["LOW", "HIGH"], histories)
    assert weights["LOW"] > weights["HIGH"]
    assert weights["LOW"] > 0.5  # concentra fuertemente en el activo de baja volatilidad


def test_risk_parity_equalizes_risk_contribution_not_dollar_weight():
    histories = {"LOW": _history(list(_synthetic_walk(300, 0.003, seed=10))),
                "HIGH": _history(list(_synthetic_walk(300, 0.04, seed=11)))}
    weights = pl._weights_risk_parity(["LOW", "HIGH"], histories)
    # Risk Parity da MAS peso en $ al activo de baja volatilidad para igualar el riesgo...
    assert weights["LOW"] > weights["HIGH"]
    # ...pero MENOS concentrado que Minimum Variance, que no le importa la contribucion, solo minimizar varianza total
    mv_weights = pl._weights_min_variance(["LOW", "HIGH"], histories)
    assert weights["LOW"] < mv_weights["LOW"]
    # y las CONTRIBUCIONES al riesgo deben quedar aproximadamente igualadas (50/50), a diferencia de Min Variance
    from pypfopt import risk_models
    prices = pd.concat({s: histories[s]["adj_close"].tail(252) for s in ["LOW", "HIGH"]}, axis=1).dropna()
    cov = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    contrib = pl.contribution_to_risk(weights, cov)
    assert contrib["LOW"] == pytest.approx(0.5, abs=0.05)
    assert contrib["HIGH"] == pytest.approx(0.5, abs=0.05)


# --- concentration_hhi / contribution_to_risk ---

def test_concentration_hhi_matches_known_values():
    assert pl.concentration_hhi({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}) == pytest.approx(0.25)
    assert pl.concentration_hhi({"A": 1.0}) == pytest.approx(1.0)
    assert pl.concentration_hhi({}) == 0.0


def test_contribution_to_risk_sums_to_one_and_favors_dominant_volatility_asset():
    histories = {"LOW": _history(list(_synthetic_walk(300, 0.003, seed=10))),
                "HIGH": _history(list(_synthetic_walk(300, 0.05, seed=11)))}
    from pypfopt import risk_models
    prices = pd.concat({s: histories[s]["adj_close"].tail(252) for s in ["LOW", "HIGH"]}, axis=1).dropna()
    cov = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
    equal_dollar_weights = {"LOW": 0.5, "HIGH": 0.5}
    contrib = pl.contribution_to_risk(equal_dollar_weights, cov)
    assert sum(contrib.values()) == pytest.approx(1.0, rel=1e-6)
    # mismo peso en $, pero el activo mucho mas volatil aporta la mayor parte del riesgo
    assert contrib["HIGH"] > contrib["LOW"]
    assert contrib["HIGH"] > 0.7


# --- apply_scenario ---

def test_scenario_sp500_down_scales_by_beta():
    weights = {"AAA": 1.0}
    result = pl.apply_scenario(weights, "sp500_-10", betas={"AAA": 2.0})
    assert result["impacto_pct"] == pytest.approx(-0.20)
    assert result["base"] == "real"


def test_scenario_tech_only_affects_tech_sector_weight():
    weights = {"TECH": 0.4, "OTHER": 0.6}
    sector_by_symbol = {"TECH": "Information Technology", "OTHER": "Financials"}
    result = pl.apply_scenario(weights, "tech_-25", sector_by_symbol=sector_by_symbol)
    assert result["impacto_pct"] == pytest.approx(0.4 * -0.25)


def test_scenario_vol_x2_doubles_annualized_volatility():
    histories = {"AAA": _history(list(_synthetic_walk(300, 0.01, seed=5)))}
    from pypfopt import risk_models
    prices = histories["AAA"]["adj_close"].tail(252).to_frame("AAA")
    cov = risk_models.CovarianceShrinkage(pd.concat({"AAA": prices["AAA"]}, axis=1)).ledoit_wolf()
    result = pl.apply_scenario({"AAA": 1.0}, "vol_x2", cov=cov)
    assert result["vol_escenario"] == pytest.approx(result["vol_base"] * 2, rel=1e-6)


def test_scenario_unknown_raises():
    with pytest.raises(ValueError):
        pl.apply_scenario({"AAA": 1.0}, "not_a_scenario")


# --- run_portfolio_lab (integracion, mode) ---

def test_run_portfolio_lab_rejects_validation_mode_with_max_symbols():
    with pytest.raises(ValueError, match="validation"):
        pl.run_portfolio_lab("2023-01-02", "2023-07-02", mode="validation", max_symbols=200)


def test_run_portfolio_lab_rejects_fast_dev_mode_without_max_symbols():
    with pytest.raises(ValueError, match="fast_dev"):
        pl.run_portfolio_lab("2023-01-02", "2023-07-02", mode="fast_dev", max_symbols=None)


def test_run_portfolio_lab_rejects_unknown_scheme():
    with pytest.raises(ValueError, match="[Ee]squemas"):
        pl.run_portfolio_lab("2023-01-02", "2023-07-02", mode="fast_dev", max_symbols=50, schemes=("bogus",))


def test_run_portfolio_lab_produces_all_requested_schemes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    # arranca un ano antes del rango analizado para que haya suficiente historial
    # (>=20 sesiones) en el momento del PRIMER rebalanceo, tras el corte point-in-time
    dates = pd.date_range("2022-01-01", "2023-10-15", freq="D")
    closes_a = list(100.0 + np.cumsum(np.random.default_rng(1).normal(0, 0.5, len(dates))))
    closes_b = list(100.0 + np.cumsum(np.random.default_rng(2).normal(0, 0.5, len(dates))))
    closes_spy = [100.0] * len(dates)
    _seed_prices(dates, [("AAA", closes_a), ("BBB", closes_b), ("SPY", closes_spy)])
    monkeypatch.setattr(pl.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})
    monkeypatch.setattr(pl.screener_asof, "build_ranking_as_of",
                        lambda day, symbols: {"table": pd.DataFrame(
                            {"composite_score": [80, 60], "score_coverage": [.9, .9], "sector": ["Tech", "Health"]},
                            index=["AAA", "BBB"])})
    result = pl.run_portfolio_lab("2023-01-02", "2023-07-02", months=3, top_n=2, initial_capital=10_000.0,
                                  schemes=("equal_weight", "inverse_vol"))
    assert set(result["schemes"]) == {"equal_weight", "inverse_vol"}
    for scheme, data in result["schemes"].items():
        assert data["nav_curve"].iloc[0] == pytest.approx(10_000.0, rel=0.05)
        assert 0 <= data["hhi"] <= 1
    assert set(result["scenarios"]["equal_weight"]) == set(pl.SCENARIOS)


def test_run_portfolio_lab_point_in_time_ignores_future_price_spike(tmp_path, monkeypatch):
    """Regresion directa del bug de look-ahead detectado durante el
    desarrollo: un pico de volatilidad DESPUES de un rebalanceo no debe
    afectar los pesos calculados EN ese rebalanceo (antes del fix, `.tail(252)`
    sobre el historial completo en cache colaba precios futuros)."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    # arranca un ano antes del rango analizado -- ver comentario equivalente arriba
    dates = pd.date_range("2022-01-01", "2023-10-15", freq="D")
    n = len(dates)
    rng_a = np.random.default_rng(1)
    closes_a = list(100.0 * np.cumprod(1 + rng_a.normal(0, 0.002, n)))
    rng_b = np.random.default_rng(2)
    closes_b = list(100.0 * np.cumprod(1 + rng_b.normal(0, 0.002, n)))
    # A partir de agosto (posterior al unico rebalanceo bajo prueba, 2023-04-02),
    # BBB se vuelve extremadamente volatil -- esto NO deberia poder influir
    # en los pesos de inverse_vol calculados en abril.
    spike_start = dates.get_loc(pd.Timestamp("2023-08-01"))
    rng_spike = np.random.default_rng(3)
    for i in range(spike_start, n):
        closes_b[i] = closes_b[i - 1] * (1 + rng_spike.normal(0, 0.5))
        closes_b[i] = max(closes_b[i], 1.0)
    closes_spy = [100.0] * n
    _seed_prices(dates, [("AAA", closes_a), ("BBB", closes_b), ("SPY", closes_spy)])
    monkeypatch.setattr(pl.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})
    monkeypatch.setattr(pl.screener_asof, "build_ranking_as_of",
                        lambda day, symbols: {"table": pd.DataFrame(
                            {"composite_score": [80, 60], "score_coverage": [.9, .9], "sector": ["Tech", "Health"]},
                            index=["AAA", "BBB"])})
    result = pl.run_portfolio_lab("2023-01-02", "2023-07-02", months=3, top_n=2, initial_capital=10_000.0,
                                  schemes=("inverse_vol",))
    weights = result["schemes"]["inverse_vol"]["last_weights"]
    # con volatilidad historica CASI IDENTICA (mismo daily_std) antes del pico futuro,
    # inverse_vol no deberia concentrarse fuertemente en ninguno de los dos
    assert weights["AAA"] == pytest.approx(0.5, abs=0.15)
    assert weights["BBB"] == pytest.approx(0.5, abs=0.15)
