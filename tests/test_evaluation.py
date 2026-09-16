import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, evaluation, storage


def _seed(symbol, p0, p1):
    df = pd.DataFrame({
        "Open": [p0, p1], "High": [p0, p1], "Low": [p0, p1],
        "Close": [p0, p1], "Adj Close": [p0, p1], "Volume": [100, 100],
    }, index=pd.to_datetime(["2024-01-02", "2024-07-02"]))
    storage.upsert_prices(symbol, df)


def test_snapshot_and_evaluation_expose_missing_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    table = pd.DataFrame({"composite_score": [80., 70., float("nan")],
                          "score_coverage": [.9, .8, .2]}, index=["AAA", "BBB", "CCC"])
    snapshot = evaluation.save_snapshot(table, "2024-01-02")
    assert evaluation.snapshot_symbols(snapshot) == ["AAA", "BBB"]
    _seed("AAA", 100, 120)
    _seed("SPY", 100, 110)
    result = evaluation.evaluate(["AAA", "BBB"], "2024-01-02", 6, cost_bps=10)
    assert result["status"] == "incomplete"
    assert result["missing"] == ["BBB"]
    assert round(result["portfolio_return"], 3) == .198
    assert round(result["benchmark_return"], 3) == .098
