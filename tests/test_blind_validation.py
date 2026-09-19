import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import blind_validation as bv
from gabi import config, storage


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")


def _seed_prices(dates, symbol_closes):
    for symbol, closes in symbol_closes:
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * len(closes)}, index=dates))


def _fake_ranking(monkeypatch, scores: dict):
    def _rank(day, symbols=None):
        syms = list(scores)
        table = pd.DataFrame({"composite_score": [scores[s] for s in syms],
                              "score_coverage": [.9] * len(syms)}, index=syms)
        return {"table": table}
    monkeypatch.setattr(bv.screener_asof, "build_ranking_as_of", _rank)


WEIGHTS = {"value": .3, "quality": .35, "momentum": .25, "risk": .1}


def test_create_validation_rejects_unlock_before_start(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        bv.create_validation("Test", WEIGHTS, 2, 3, "2027-01-01", "2026-01-01")


def test_record_rebalance_is_immutable_for_the_same_date(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    _seed_prices(dates, [("A", [100.0] * 10), ("B", [50.0] * 10)])
    _fake_ranking(monkeypatch, {"A": 90, "B": 80})
    vid = bv.create_validation("Test", WEIGHTS, 2, 3, "2024-01-10", "2099-01-01")

    result = bv.record_rebalance(vid, as_of="2024-01-10")
    assert result["symbols"] == ["A", "B"]
    assert result["entry_prices"] == {"A": 100.0, "B": 50.0}

    with pytest.raises(ValueError, match="inmutable"):
        bv.record_rebalance(vid, as_of="2024-01-10")


def test_get_status_hides_performance_while_locked(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    _seed_prices(dates, [("A", [100.0] * 10), ("SPY", [400.0] * 10)])
    _fake_ranking(monkeypatch, {"A": 90})
    vid = bv.create_validation("Test", WEIGHTS, 1, 3, "2024-01-10", "2099-01-01")
    bv.record_rebalance(vid, as_of="2024-01-10")

    status = bv.get_status(vid)
    assert status["revealed"] is False
    assert "performance" not in status
    assert "retorno" not in status
    assert status["n_periods"] == 1


def test_get_status_reveals_performance_when_reveal_true(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    _seed_prices(dates, [("A", [100.0] * 5 + [110.0] * 5), ("SPY", [400.0] * 5 + [408.0] * 5)])
    _fake_ranking(monkeypatch, {"A": 90})
    vid = bv.create_validation("Test", WEIGHTS, 1, 3, "2024-01-01", "2099-01-01")
    bv.record_rebalance(vid, as_of="2024-01-01")

    status = bv.get_status(vid, reveal=True)
    assert status["revealed"] is True
    perf = status["performance"]["periods"][0]
    assert perf["retorno"] == pytest.approx(0.10, abs=1e-6)
    assert perf["retorno_spy"] == pytest.approx(0.02, abs=1e-6)


def test_get_status_auto_reveals_after_unlock_date(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    _seed_prices(dates, [("A", [100.0] * 10)])
    _fake_ranking(monkeypatch, {"A": 90})
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    vid = bv.create_validation("Test", WEIGHTS, 1, 3, "2024-01-01", yesterday)
    bv.record_rebalance(vid, as_of="2024-01-01")
    assert bv.get_status(vid)["revealed"] is True


def test_verify_integrity_detects_manual_tampering(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    _seed_prices(dates, [("A", [100.0] * 10), ("B", [50.0] * 10)])
    _fake_ranking(monkeypatch, {"A": 90, "B": 80})
    vid = bv.create_validation("Test", WEIGHTS, 2, 3, "2024-01-10", "2099-01-01")
    bv.record_rebalance(vid, as_of="2024-01-10")
    assert bv.verify_integrity(vid)["ok"] is True

    with storage.get_connection() as conn:
        conn.execute("UPDATE blind_validation_periods SET entry_prices_json = ? WHERE validation_id = ?",
                     ('{"A": 999.0, "B": 50.0}', vid))
        conn.commit()

    result = bv.verify_integrity(vid)
    assert result["ok"] is False
    assert result["broken_at"] == "2024-01-10"


def test_break_seal_early_requires_a_reason_and_reveals(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    _seed_prices(dates, [("A", [100.0] * 10)])
    _fake_ranking(monkeypatch, {"A": 90})
    vid = bv.create_validation("Test", WEIGHTS, 1, 3, "2024-01-01", "2099-01-01")
    bv.record_rebalance(vid, as_of="2024-01-01")

    with pytest.raises(ValueError):
        bv.break_seal_early(vid, "")

    bv.break_seal_early(vid, "Curiosidad, asumo el sesgo")
    status = bv.get_status(vid)
    assert status["revealed"] is True
    assert status["status"] == "broken_early"


def test_export_to_research_lab_requires_revealed_validation(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    _seed_prices(dates, [("A", [100.0] * 10), ("SPY", [400.0] * 10)])
    _fake_ranking(monkeypatch, {"A": 90})
    vid = bv.create_validation("Test", WEIGHTS, 1, 3, "2024-01-01", "2099-01-01")
    bv.record_rebalance(vid, as_of="2024-01-01")

    with pytest.raises(ValueError, match="bloqueada"):
        bv.export_to_research_lab(vid)

    bv.break_seal_early(vid, "prueba")
    exp_id = bv.export_to_research_lab(vid)
    assert exp_id > 0
