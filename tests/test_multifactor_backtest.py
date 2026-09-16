import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, multifactor_backtest as bt, storage


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


def test_rejects_approximate_historical_universe(monkeypatch):
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": False, "note": "fuera de cobertura"})
    with pytest.raises(ValueError, match="composición histórica"):
        bt.run("2023-01-02", "2023-04-02")


def test_rejects_insufficient_universe_coverage(monkeypatch):
    monkeypatch.setattr(bt.universe, "get_sp500_constituents_asof",
                        lambda day: {"is_exact": True, "symbols": ["AAA", "BBB"], "note": ""})
    monkeypatch.setattr(bt.screener_asof, "build_ranking_as_of",
                        lambda day, symbols: {"table": pd.DataFrame({
                            "composite_score": [80, None], "score_coverage": [.9, 0]}, index=symbols)})
    with pytest.raises(ValueError, match="cobertura insuficiente"):
        bt.run("2023-01-02", "2023-04-02", top_n=1)


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
