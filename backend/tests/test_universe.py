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


def test_get_sp500_constituents_asof_after_coverage_raises_without_current_fallback(tmp_path, monkeypatch):
    cache = tmp_path / "hist.csv"
    _write_history(cache, [("2018-01-01", "AAA,BBB")])
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", cache)

    monkeypatch.setattr(universe, "get_sp500_constituents",
                        lambda: (_ for _ in ()).throw(AssertionError("current universe used")))

    import pytest
    with pytest.raises(ValueError, match="después de 2018-01-01"):
        universe.get_sp500_constituents_asof("2099-01-01")


def test_get_sp500_constituents_asof_blocks_conflicting_snapshot_until_next_date(tmp_path, monkeypatch):
    cache = tmp_path / "hist.csv"
    _write_history(cache, [("2018-01-01", "AAA"), ("2018-03-01", "AAA"),
                           ("2018-03-01", "BBB"), ("2018-04-01", "CCC")])
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", cache)
    import pytest
    with pytest.raises(ValueError, match="contradictoria"):
        universe.get_sp500_constituents_asof("2018-03-15")
    assert universe.get_sp500_constituents_asof("2018-04-01")["symbols"] == ["CCC"]


def test_reviewed_wlp_label_replaces_retrospective_antm_only_before_change(tmp_path, monkeypatch):
    cache = tmp_path / "hist.csv"
    _write_history(cache, [("2009-12-01", "AAA,ANTM"), ("2014-12-03", "AAA,ANTM"), ("2016-02-01", "AAA,ANTM")])
    monkeypatch.setattr(universe, "HISTORICAL_MEMBERSHIP_CACHE", cache)
    # 2010-2015 uses the accredited reference layer (#32); these dates test
    # the operational source on both sides of that window.
    before = universe.get_sp500_constituents_asof("2009-12-15")
    assert before["symbols"] == ["AAA", "WLP"]
    assert before["label_corrections"][0]["reported_symbol"] == "ANTM"
    after = universe.get_sp500_constituents_asof("2016-01-15")
    assert after["symbols"] == ["AAA", "ANTM"]
    assert after["label_corrections"] == []
