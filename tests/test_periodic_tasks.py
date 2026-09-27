from datetime import UTC, date, datetime

import pandas as pd

from gabi import blind_validation as bv
from gabi import config, storage
from gabi import periodic_tasks as pt

WEIGHTS = {"value": .3, "quality": .35, "momentum": .25, "risk": .1}
AFTER_CLOSE = datetime(2024, 1, 10, 22, tzinfo=UTC)  # miércoles, tras el cierre: última sesión 2024-01-10


def _seed(last_day: str, symbols=("SPY", "RSP", "A")):
    dates = pd.date_range("2024-01-02", last_day, freq="B")
    closes = [100.0] * len(dates)
    for symbol in symbols:
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                                                    "Adj Close": closes, "Volume": [1] * len(dates)}, index=dates))


def _calls(monkeypatch) -> list:
    calls: list = []

    def record(validation_id, as_of=None):
        calls.append(validation_id)
        return {"rebalance_date": "2024-01-10", "symbols": ["A"], "record_hash": "h"}
    monkeypatch.setattr(bv, "record_rebalance", record)
    return calls


def test_stale_prices_block_a_due_rebalance(monkeypatch):
    _seed("2024-01-08")
    vid = bv.create_validation("Prueba", WEIGHTS, 1, 3, "2024-01-10", "2099-01-01")
    calls = _calls(monkeypatch)
    outcome = pt.record_due(AFTER_CLOSE)
    assert calls == []
    assert outcome[0]["id"] == vid and not outcome[0]["registrado"]
    assert "precios no actualizados" in outcome[0]["motivo"]


def test_missing_rsp_blocks_even_with_fresh_spy(monkeypatch):
    _seed("2024-01-10", symbols=("SPY", "A"))
    bv.create_validation("Prueba", WEIGHTS, 1, 3, "2024-01-10", "2099-01-01")
    calls = _calls(monkeypatch)
    assert not pt.prices_fresh(AFTER_CLOSE)
    assert not pt.record_due(AFTER_CLOSE)[0]["registrado"] and calls == []


def test_fresh_prices_record_only_due_rebalances(monkeypatch):
    _seed("2024-01-10")
    due = bv.create_validation("Vence hoy", WEIGHTS, 1, 3, "2024-01-10", "2099-01-01")
    bv.create_validation("Vence después", WEIGHTS, 1, 3, "2024-03-01", "2099-01-01")
    calls = _calls(monkeypatch)
    outcome = pt.record_due(AFTER_CLOSE)
    assert calls == [due]
    assert outcome == [{"id": due, "registrado": True, "fecha": "2024-01-10", "hash": "h", "posiciones": 1}]


def test_before_the_close_the_previous_session_is_required(monkeypatch):
    _seed("2024-01-09")
    before_close = datetime(2024, 1, 10, 15, tzinfo=UTC)
    assert pt.last_session(before_close) == "2024-01-09"
    assert pt.prices_fresh(before_close)


def test_status_writes_nothing(monkeypatch):
    _seed("2024-01-10")
    bv.create_validation("Prueba", WEIGHTS, 1, 3, "2024-01-10", "2099-01-01")
    calls = _calls(monkeypatch)
    report = pt.status(AFTER_CLOSE)
    assert calls == [] and not pt.log_path().exists()
    assert report["precios_al_dia"] and report["pruebas_ciegas"][0]["vencido"]
    assert report["tiingo_44"] == {"cola": 0, "descargados": 0, "en_curso": False}


def test_due_soon_flags_the_next_seven_days():
    bv.create_validation("Pronto", WEIGHTS, 1, 3, "2024-01-15", "2099-01-01")
    bv.create_validation("Lejos", WEIGHTS, 1, 3, "2024-02-15", "2099-01-01")
    soon = pt.due_soon(today=date(2024, 1, 10))
    assert [row["nombre"] for row in soon] == ["Pronto"] and soon[0]["dias"] == 5


def test_tiingo_resume_skips_when_already_running():
    pt.tiingo_lock_path().parent.mkdir(parents=True)
    pt.tiingo_lock_path().write_text("x")
    assert "en curso" in pt.resume_tiingo()["omitido"]


def test_tiingo_resume_releases_the_lock(monkeypatch):
    from gabi import historical_tiingo
    pt.tiingo_queue_path().parent.mkdir(parents=True)
    pt.tiingo_queue_path().write_text("abc xyz")
    seen = {}
    monkeypatch.setattr(historical_tiingo, "fetch", lambda symbols, window: seen.update(symbols=symbols) or {})
    monkeypatch.setattr(historical_tiingo, "import_cached", lambda window: {})
    pt.resume_tiingo()
    assert seen["symbols"] == ["ABC", "XYZ"] and not pt.tiingo_lock_path().exists()
    assert pt.log_path().exists() and pt.log_path().is_relative_to(config.DATA_DIR)
