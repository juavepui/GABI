import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, edgar, portfolio_backtest as pb, storage


def _seed_prices(dates, symbol_closes):
    for symbol, closes in symbol_closes:
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * len(closes)}, index=dates))


def _seed_filing(symbol, filed_date):
    edgar.upsert_edgar_facts(symbol, [{
        "tag": "NetIncomeLoss", "unit": "USD", "start_date": "2020-01-01", "end_date": "2020-12-31",
        "val": 1, "form": "10-K", "fp": "FY", "fy": 2020, "filed_date": filed_date, "accn": "0001-20-000001",
    }])


# --- _apply_trade ---

def test_apply_trade_buy_charges_fixed_commission_and_spread():
    cash = 1000.0
    shares = {}
    cash = pb._apply_trade(cash, shares, "AAA", "BUY", 500.0, price=100.0,
                           commission_usd=1.0, spread_bps=10.0)
    assert cash == pytest.approx(1000 - 500 - 1.0)
    assert shares["AAA"] == pytest.approx(500 / (100 * (1 + 10 / 20000)))


def test_apply_trade_sell_charges_fixed_commission_and_spread():
    cash = 0.0
    shares = {"AAA": 5.0}
    cash = pb._apply_trade(cash, shares, "AAA", "SELL", 500.0, price=100.0,
                           commission_usd=1.0, spread_bps=10.0)
    assert cash == pytest.approx(500 * (1 - 10 / 20000) - 1.0)
    assert "AAA" not in shares  # venta entera de la posicion: no queda un residuo casi-cero


def test_apply_trade_skips_zero_notional_without_commission():
    cash = 1000.0
    shares = {}
    result = pb._apply_trade(cash, shares, "AAA", "BUY", 0.0, price=100.0,
                             commission_usd=1.0, spread_bps=10.0)
    assert result == cash
    assert shares == {}


def test_apply_trade_rejects_unknown_side():
    with pytest.raises(ValueError):
        pb._apply_trade(100.0, {}, "AAA", "HOLD", 50.0, 10.0, 1.0, 0.0)


# --- _rebalance ---

def test_rebalance_no_cost_when_held_position_already_at_target_weight():
    shares = {"AAA": 10.0}  # AAA vale 1000, cartera total con caja = 2000, top_n=2 -> target 1000
    entry_price = {"AAA": 100.0, "BBB": 50.0}
    result = pb._rebalance(cash=1000.0, shares=shares, picks=["AAA", "BBB"],
                           entry_price=entry_price, top_n=2, commission_usd=1.0, spread_bps=0.0)
    assert result["held"] == {"AAA"}
    assert result["bought"] == {"BBB"}
    assert result["comision_pagada"] == pytest.approx(1.0)  # solo la compra de BBB, AAA no se toca


def test_rebalance_trims_held_position_that_drifted_from_target_weight():
    shares = {"AAA": 10.0}  # AAA subio a 150 -> vale 1500, unica posicion
    entry_price = {"AAA": 150.0, "BBB": 50.0}
    result = pb._rebalance(cash=0.0, shares=shares, picks=["AAA", "BBB"],
                           entry_price=entry_price, top_n=2, commission_usd=1.0, spread_bps=0.0)
    # portfolio_value = 1500; target = 750 cada una.
    assert result["held"] == {"AAA"}
    assert result["bought"] == {"BBB"}
    assert shares["AAA"] * 150.0 == pytest.approx(750.0)  # recortada exactamente al peso objetivo
    assert result["comision_pagada"] == pytest.approx(2.0)  # recorte de AAA + compra de BBB


def test_rebalance_sells_full_position_for_exited_symbol():
    shares = {"AAA": 10.0}
    entry_price = {"AAA": 100.0, "BBB": 50.0}
    result = pb._rebalance(cash=0.0, shares=shares, picks=["BBB"],
                           entry_price=entry_price, top_n=1, commission_usd=1.0, spread_bps=0.0)
    assert result["sold"] == {"AAA"}
    assert "AAA" not in shares
    assert result["bought"] == {"BBB"}
    assert result["comision_pagada"] == pytest.approx(2.0)  # venta AAA + compra BBB


def test_rebalance_conserves_value_minus_commissions():
    shares = {"AAA": 10.0, "CCC": 4.0}
    entry_price = {"AAA": 100.0, "BBB": 50.0, "CCC": 25.0}
    before_value = shares["AAA"] * 100 + shares["CCC"] * 25
    result = pb._rebalance(cash=0.0, shares=shares, picks=["AAA", "BBB"],
                           entry_price=entry_price, top_n=2, commission_usd=1.0, spread_bps=0.0)
    after_value = result["cash"] + sum(shares[s] * entry_price[s] for s in shares)
    assert after_value == pytest.approx(before_value - result["comision_pagada"])


def test_rebalance_charges_spread_on_traded_amount_only():
    shares = {}
    entry_price = {"AAA": 100.0}
    result = pb._rebalance(cash=1000.0, shares=shares, picks=["AAA"],
                           entry_price=entry_price, top_n=1, commission_usd=0.0, spread_bps=200.0)
    # target = 1000; spread 200pb -> half = 1%. shares = 1000 / (100*1.01)
    assert shares["AAA"] == pytest.approx(1000 / (100 * 1.01))


# --- buy_and_hold_curve ---

def test_buy_and_hold_curve_pays_commission_once(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    _seed_prices(dates, [("SPY", [100.0, 101.0, 99.0, 102.0])])
    curve = pb.buy_and_hold_curve("SPY", "2024-01-02", "2024-01-05",
                                  initial_capital=10_000.0, commission_usd=1.0, spread_bps=0.0)
    shares_bought = (10_000.0 - 1.0) / 100.0
    assert curve.iloc[0] == pytest.approx(shares_bought * 100.0, rel=1e-9)
    assert curve.iloc[-1] == pytest.approx(shares_bought * 102.0, rel=1e-9)
    # ninguna operacion mas: el valor sigue el precio 1 a 1 en todo el tramo
    assert curve.iloc[2] == pytest.approx(shares_bought * 99.0, rel=1e-9)


# --- run() (integracion, con monkeypatch del ranking) ---

def test_run_rebalances_using_each_periods_ranking(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.date_range("2023-01-01", "2023-10-15", freq="D")
    _seed_prices(dates, [("AAA", [100.0] * len(dates)), ("BBB", [100.0] * len(dates)),
                        ("SPY", [100.0] * len(dates))])
    monkeypatch.setattr(pb.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})

    seen = []

    def rank(day, symbols):
        seen.append(day)
        winner = "AAA" if len(seen) == 1 else "BBB"
        loser = "BBB" if winner == "AAA" else "AAA"
        return {"table": pd.DataFrame({"composite_score": [80, 70], "score_coverage": [.9, .9]},
                                      index=[winner, loser])}

    monkeypatch.setattr(pb.screener_asof, "build_ranking_as_of", rank)
    result = pb.run("2023-01-02", "2023-07-02", months=3, top_n=1, initial_capital=10_000.0)
    assert seen == ["2023-01-02", "2023-04-02"]
    assert result["periods"]["bought"].tolist() == ["AAA", "BBB"]
    # precios constantes -> sin ganancia/perdida, solo comisiones
    assert result["capital_final"] < 10_000.0
    assert result["comision_total"] > 0


def test_run_nav_curve_stays_flat_through_skipped_period_no_gap(tmp_path, monkeypatch):
    """Un periodo sin cobertura suficiente no debe dejar un hueco en la
    curva NAV -- la cartera sigue flotando con lo que ya tenia (a
    diferencia de V1)."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.date_range("2023-01-01", "2023-10-15", freq="D")
    _seed_prices(dates, [("AAA", [100.0] * len(dates)), ("SPY", [100.0] * len(dates))])
    monkeypatch.setattr(pb.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA"], "note": ""})

    def rank(day, symbols):
        if day == "2023-04-02":  # segundo periodo: sin cobertura suficiente
            return {"table": pd.DataFrame({"composite_score": [None], "score_coverage": [0]}, index=["AAA"])}
        return {"table": pd.DataFrame({"composite_score": [80], "score_coverage": [.9]}, index=["AAA"])}

    monkeypatch.setattr(pb.screener_asof, "build_ranking_as_of", rank)
    result = pb.run("2023-01-02", "2023-10-02", months=3, top_n=1, initial_capital=10_000.0)
    assert len(result["skipped"]) == 1
    # la curva NAV no tiene huecos: cubre todo el rango de sesiones, incluido el periodo saltado
    full_range = result["nav_curve"].index
    assert full_range.is_monotonic_increasing
    assert (full_range.to_series().diff().dropna().dt.days <= 4).all()  # sin saltos de mas de un fin de semana largo


def test_run_ignores_future_filing_from_recycled_ticker(tmp_path, monkeypatch):
    """Regresion: el guard de reciclaje de ticker de V1 debe seguir
    funcionando en V2 (se reutiliza v1._MAX_DAYS_WITHOUT_FILING)."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.date_range("2016-01-01", "2016-10-15", freq="D")
    _seed_prices(dates, [("AAA", [100.0] * len(dates)), ("SPY", [100.0] * len(dates))])
    _seed_filing("AAA", "2010-01-01")  # ultimo filing conocido HASTA el periodo: demasiado viejo -> reciclado
    edgar.upsert_edgar_facts("AAA", [{  # filing futuro (empresa nueva que se quedo el ticker): debe ignorarse
        "tag": "NetIncomeLoss", "unit": "USD", "start_date": "2025-01-01", "end_date": "2025-12-31",
        "val": 1, "form": "10-K", "fp": "FY", "fy": 2025, "filed_date": "2025-01-01", "accn": "0002-25-000001",
    }])
    monkeypatch.setattr(pb.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA"], "note": ""})
    monkeypatch.setattr(pb.screener_asof, "build_ranking_as_of",
                        lambda day, symbols: {"table": pd.DataFrame(
                            {"composite_score": [80], "score_coverage": [.9]}, index=["AAA"])})
    with pytest.raises(ValueError, match="Ningún periodo"):
        pb.run("2016-01-02", "2016-07-02", months=3, top_n=1, initial_capital=10_000.0)
