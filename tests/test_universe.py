import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import universe


def _write_history(path, rows):
    pd.DataFrame(rows, columns=["date", "tickers"]).to_csv(path, index=False)


def test_get_sp500_constituents_asof_exact_snapshot_date(tmp_path, monkeypatch):
    cache = tmp_path / "hist.csv"
    _write_history(cache, [
        ("2018-01-01", "AAA,BBB,CCC"),
        ("2019-06-01", "AAA,BBB,DDD"),  # CCC salió, entró DDD
        ("2020-01-01", "AAA,BBB,DDD,EEE"),
    ])
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", cache)

    result = universe.get_sp500_constituents_asof("2019-06-01")
    assert result["is_exact"] is True
    assert result["source_date"] == "2019-06-01"
    assert set(result["symbols"]) == {"AAA", "BBB", "DDD"}


def test_get_sp500_constituents_asof_uses_most_recent_snapshot_before_date(tmp_path, monkeypatch):
    cache = tmp_path / "hist.csv"
    _write_history(cache, [
        ("2018-01-01", "AAA,BBB,CCC"),
        ("2019-06-01", "AAA,BBB,DDD"),
        ("2020-01-01", "AAA,BBB,DDD,EEE"),
    ])
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", cache)

    # 2019-09-15 está entre el snapshot de 2019-06-01 y el de 2020-01-01:
    # debe devolver la composición de 2019-06-01 (la vigente en ese momento),
    # sin adelantar información del cambio que aún no había pasado (EEE).
    result = universe.get_sp500_constituents_asof("2019-09-15")
    assert result["is_exact"] is True
    assert result["source_date"] == "2019-06-01"
    assert set(result["symbols"]) == {"AAA", "BBB", "DDD"}
    assert "EEE" not in result["symbols"]  # sin look-ahead bias en el universo tampoco


def test_get_sp500_constituents_asof_before_coverage_raises(tmp_path, monkeypatch):
    cache = tmp_path / "hist.csv"
    _write_history(cache, [("2018-01-01", "AAA,BBB")])
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", cache)

    import pytest
    with pytest.raises(ValueError):
        universe.get_sp500_constituents_asof("2000-01-01")


def test_get_sp500_constituents_asof_after_coverage_falls_back_to_current(tmp_path, monkeypatch):
    cache = tmp_path / "hist.csv"
    _write_history(cache, [("2018-01-01", "AAA,BBB")])
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", cache)

    current_df = pd.DataFrame({
        "symbol": ["ZZZ", "YYY"], "name": ["Z Corp", "Y Corp"],
        "sector": ["Tech", "Tech"], "industry": ["Software", "Software"],
    })
    monkeypatch.setattr(universe, "get_sp500_constituents", lambda: current_df)

    result = universe.get_sp500_constituents_asof("2099-01-01")
    assert result["is_exact"] is False
    assert result["source_date"] is None
    assert set(result["symbols"]) == {"ZZZ", "YYY"}
    assert "sesgo de supervivencia" in result["note"]
