import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, edgar, multifactor_backtest as bt, storage


def _seed_prices(dates, symbol_closes):
    for symbol, closes in symbol_closes:
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * len(closes)}, index=dates))


def _seed_filing(symbol, filed_date):
    edgar.upsert_edgar_facts(symbol, [{
        "tag": "NetIncomeLoss", "unit": "USD", "start_date": "2020-01-01", "end_date": "2020-12-31",
        "val": 1, "form": "10-K", "fp": "FY", "fy": 2020, "filed_date": filed_date, "accn": "0001-20-000001",
    }])


def test_rebalances_using_each_periods_ranking(monkeypatch):
    seen = []
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})

    def rank(day, symbols):
        seen.append(day)
        winner = "AAA" if len(seen) == 1 else "BBB"
        return {"table": pd.DataFrame({"composite_score": [80, 70], "score_coverage": [.9, .9]},
                                      index=[winner, "BBB" if winner == "AAA" else "AAA"])}

    monkeypatch.setattr(bt.screener_asof, "build_ranking_as_of", rank)
    monkeypatch.setattr(bt, "_period_returns",
                        lambda symbols, day, months, cost: {"end_date": str(day.date()),
                                                             "portfolio_return": .1, "benchmark_return": .05})
    result = bt.run("2023-01-02", "2023-07-02", months=3, top_n=1)
    assert seen == ["2023-01-02", "2023-04-02"]
    assert result["periods"]["candidatas"].tolist() == ["AAA", "BBB"]
    assert result["return"] == pytest.approx(.21)


def test_required_symbols_unions_memberships(monkeypatch):
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True,
                                     "symbols": ["AAA"] if day.endswith("01-02") else ["BBB"]})
    assert bt.required_symbols("2023-01-02", "2023-07-02", 3) == ["AAA", "BBB"]


def test_rejects_when_every_period_lacks_coverage(monkeypatch):
    """Si TODOS los periodos del rango carecen de composición histórica
    verificable, no hay nada que backtest-ear: debe fallar."""
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": False, "note": "fuera de cobertura"})
    with pytest.raises(ValueError, match="Ningún periodo"):
        bt.run("2023-01-02", "2023-04-02")


def test_skips_single_bad_period_instead_of_aborting_whole_range(monkeypatch):
    """Un solo trimestre sin cobertura suficiente (frecuente en años con poca
    cobertura SEC EDGAR) no debe tumbar todo el backtest — se salta y se
    sigue con los periodos que sí tienen datos."""
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})

    def rank(day, symbols):
        if day == "2023-01-02":  # primer periodo: sin cobertura suficiente
            return {"table": pd.DataFrame({"composite_score": [80, None], "score_coverage": [.9, 0]},
                                          index=symbols)}
        return {"table": pd.DataFrame({"composite_score": [80, 70], "score_coverage": [.9, .9]},
                                      index=symbols)}

    monkeypatch.setattr(bt.screener_asof, "build_ranking_as_of", rank)
    monkeypatch.setattr(bt, "_period_returns",
                        lambda symbols, day, months, cost: {"end_date": str(day.date()),
                                                             "portfolio_return": .1, "benchmark_return": .05})
    result = bt.run("2023-01-02", "2023-07-02", months=3, top_n=1)
    assert len(result["periods"]) == 1
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["fecha"] == "2023-01-02"
    assert "cobertura insuficiente" in result["skipped"][0]["motivo"]


def test_period_buys_after_signal_session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-02-05"])
    for symbol, closes in (("AAA", [100, 200, 220]), ("SPY", [100, 100, 110])):
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * 3}, index=dates))
    result = bt._period_returns(["AAA"], pd.Timestamp("2024-01-05"), 1, 0)
    assert result["portfolio_return"] == pytest.approx(.1)
    assert result["benchmark_return"] == pytest.approx(.1)


def test_risk_metrics_on_steady_positive_returns():
    """Una serie de retornos trimestrales positivos (con algo de variación,
    si no la volatilidad es 0 y Sharpe queda indefinido) debe dar
    Sharpe/Sortino positivos y drawdown cero (nunca cae respecto a su máximo)."""
    returns = pd.Series([.02, -.01, .03, .05])
    m = bt._risk_metrics(returns, periods_per_year=4)
    assert m["anualizado"] > 0
    assert m["sharpe"] > 0
    assert m["sortino"] > 0
    assert m["max_drawdown"] < 0


def test_risk_metrics_flags_drawdown_after_a_loss():
    returns = pd.Series([.10, -.20, .05])
    m = bt._risk_metrics(returns, periods_per_year=4)
    assert m["max_drawdown"] < 0


def test_run_includes_universo_ew_benchmark_and_metrics(monkeypatch):
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})
    monkeypatch.setattr(bt.screener_asof, "build_ranking_as_of",
                        lambda day, symbols: {"table": pd.DataFrame(
                            {"composite_score": [80, 70], "score_coverage": [.9, .9]}, index=symbols)})

    def fake_period_returns(symbols, day, months, cost):
        # El universo completo (2 empresas) rinde distinto que el top-1, para
        # poder comprobar que no son la misma columna por accidente.
        portfolio_return = .1 if len(symbols) == 1 else .04
        return {"end_date": str(day.date()), "portfolio_return": portfolio_return, "benchmark_return": .05}

    monkeypatch.setattr(bt, "_period_returns", fake_period_returns)
    result = bt.run("2023-01-02", "2023-04-02", months=3, top_n=1)
    assert result["periods"]["universo_ew"].iloc[0] == pytest.approx(.04)
    assert result["universo_ew_return"] == pytest.approx(.04)
    assert set(result["metrics"]) == {"estrategia", "universo_ew", "spy"}


def test_period_returns_rejects_symbol_with_no_recent_sec_filing(tmp_path, monkeypatch):
    """Si una empresa lleva años sin presentar nada ante la SEC pero yfinance
    sigue devolviendo cotización 'viva' bajo su ticker, lo más probable es
    que la bolsa haya reciclado ese símbolo a otra empresa distinta (caso
    real comprobado: BBBY) — debe rechazarse en vez de usarse en silencio."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-02-05"])
    _seed_prices(dates, [("ZOMBIE", [100, 200, 220]), ("SPY", [100, 100, 110])])
    _seed_filing("ZOMBIE", "2018-01-01")  # ultimo filing hace mas de 450 dias
    with pytest.raises(ValueError, match="reciclado"):
        bt._period_returns(["ZOMBIE"], pd.Timestamp("2024-01-05"), 1, 0)


def test_period_returns_accepts_symbol_with_recent_sec_filing(tmp_path, monkeypatch):
    """Una empresa que sí sigue presentando filings regularmente no debe
    activar la comprobación de reciclaje, aunque tenga historial en edgar_facts."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    dates = pd.to_datetime(["2024-01-05", "2024-01-08", "2024-02-05"])
    _seed_prices(dates, [("AAA", [100, 200, 220]), ("SPY", [100, 100, 110])])
    _seed_filing("AAA", "2024-01-01")  # filing reciente, empresa viva
    result = bt._period_returns(["AAA"], pd.Timestamp("2024-01-05"), 1, 0)
    assert result["portfolio_return"] == pytest.approx(.1)
