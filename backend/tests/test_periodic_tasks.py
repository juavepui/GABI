from datetime import UTC, date, datetime

import pandas as pd
import pytest

from gabi import blind_validation as bv
from gabi import config, storage
from gabi.infrastructure.legacy.periodic import build_periodic_tasks

WEIGHTS = {"value": .3, "quality": .35, "momentum": .25, "risk": .1}
AFTER_CLOSE = datetime(2024, 1, 10, 22, tzinfo=UTC)  # miércoles, tras el cierre: última sesión 2024-01-10


def _seed(last_day: str, symbols=("SPY", "RSP", "A")):
    dates = pd.date_range("2024-01-02", last_day, freq="B")
    closes = [100.0] * len(dates)
    for symbol in symbols:
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                                                    "Adj Close": closes, "Volume": [1] * len(dates)}, index=dates))


@pytest.fixture
def pt(monkeypatch):
    service = build_periodic_tasks(config.DATA_DIR)
    monkeypatch.setattr(service, "live_symbols", lambda: ["A"])
    return service


def _calls(monkeypatch) -> list:
    calls: list = []

    def record(validation_id, as_of=None):
        calls.append(validation_id)
        return {"rebalance_date": "2024-01-10", "symbols": ["A"], "record_hash": "h"}
    monkeypatch.setattr(bv, "record_rebalance", record)
    return calls


def test_stale_prices_block_a_due_rebalance(pt, monkeypatch):
    _seed("2024-01-08")
    vid = bv.create_validation("Prueba", WEIGHTS, 1, 3, "2024-01-10", "2099-01-01")
    calls = _calls(monkeypatch)
    outcome = pt.record_due(AFTER_CLOSE)
    assert calls == []
    assert outcome[0]["id"] == vid and not outcome[0]["registrado"]
    assert "precios no actualizados" in outcome[0]["motivo"]


def test_missing_rsp_blocks_even_with_fresh_spy(pt, monkeypatch):
    _seed("2024-01-10", symbols=("SPY", "A"))
    bv.create_validation("Prueba", WEIGHTS, 1, 3, "2024-01-10", "2099-01-01")
    calls = _calls(monkeypatch)
    assert not pt.prices_fresh(AFTER_CLOSE)
    assert not pt.record_due(AFTER_CLOSE)[0]["registrado"] and calls == []


def test_fresh_prices_record_only_due_rebalances(pt, monkeypatch):
    _seed("2024-01-10")
    due = bv.create_validation("Vence hoy", WEIGHTS, 1, 3, "2024-01-10", "2099-01-01")
    bv.create_validation("Vence después", WEIGHTS, 1, 3, "2024-03-01", "2099-01-01")
    calls = _calls(monkeypatch)
    outcome = pt.record_due(AFTER_CLOSE)
    assert calls == [due]
    assert outcome == [{"id": due, "registrado": True, "fecha": "2024-01-10", "hash": "h", "posiciones": 1}]


def test_symbols_outside_the_live_universe_do_not_count(pt):
    _seed("2024-01-10")
    _seed("2024-01-08", symbols=("OLD",))
    assert pt.stale_share(AFTER_CLOSE) == 0 and pt.prices_fresh(AFTER_CLOSE)


def test_before_the_close_the_previous_session_is_required(pt, monkeypatch):
    _seed("2024-01-09")
    before_close = datetime(2024, 1, 10, 15, tzinfo=UTC)
    assert pt.last_session(before_close) == "2024-01-09"
    assert pt.prices_fresh(before_close)


def test_status_writes_nothing(pt, monkeypatch):
    _seed("2024-01-10")
    bv.create_validation("Prueba", WEIGHTS, 1, 3, "2024-01-10", "2099-01-01")
    calls = _calls(monkeypatch)
    report = pt.status(AFTER_CLOSE)
    assert calls == [] and not pt.store.log_path.exists()
    assert report["precios_al_dia"] and report["pruebas_ciegas"][0]["vencido"]
    assert report["tiingo_44"] == {"cola": 0, "descargados": 0, "en_curso": False}


def test_due_soon_flags_the_next_seven_days(pt):
    bv.create_validation("Pronto", WEIGHTS, 1, 3, "2024-01-15", "2099-01-01")
    bv.create_validation("Lejos", WEIGHTS, 1, 3, "2024-02-15", "2099-01-01")
    soon = pt.due_soon(today=date(2024, 1, 10))
    assert [row["nombre"] for row in soon] == ["Pronto"] and soon[0]["dias"] == 5


def test_tiingo_resume_skips_when_already_running(pt):
    pt.store.lock_path.parent.mkdir(parents=True)
    pt.store.lock_path.write_text("x")
    assert "en curso" in pt.resume_tiingo()["omitido"]


def test_tiingo_resume_releases_the_lock(pt, monkeypatch, tmp_path):
    from gabi import historical_tiingo, smallmid_test
    monkeypatch.setattr(smallmid_test, "WORK", tmp_path)
    pt.store.complete = smallmid_test.tiingo_complete_path()
    pt.store.queue_path.parent.mkdir(parents=True)
    pt.store.queue_path.write_text("abc xyz")
    seen = {}
    monkeypatch.setattr(historical_tiingo, "fetch", lambda symbols, window: seen.update(symbols=symbols) or {})
    monkeypatch.setattr(historical_tiingo, "import_cached", lambda window: {})
    pt.resume_tiingo()
    assert seen["symbols"] == ["ABC", "XYZ"] and not pt.store.lock_path.exists()
    assert pt.store.log_path.exists() and pt.store.log_path.is_relative_to(config.DATA_DIR)
    assert (tmp_path / "tiingo_completa.json").exists()  # cola recorrida sin tope: A3 congela los datos


def test_smallmid_final_step_runs_once_when_frozen(pt, monkeypatch):
    from gabi import smallmid_test as sm
    calls = []
    monkeypatch.setattr(sm, "final_run", lambda: calls.append(1) or {"decision_a1": "x"})
    assert not pt.smallmid_step(date(2026, 10, 1))["lanzado"] and calls == []  # aún sin congelar
    assert pt.smallmid_step(date(2027, 1, 15))["lanzado"] and calls == [1]
    sm.result_path().parent.mkdir(parents=True)
    sm.result_path().write_text("{}")
    assert not pt.smallmid_step(date(2027, 2, 1))["lanzado"] and calls == [1]  # ya analizado: nunca se repite


def test_smallmid_failure_does_not_break_maintenance(pt, monkeypatch):
    from gabi import smallmid_test as sm

    def boom():
        raise RuntimeError("sin red")
    monkeypatch.setattr(sm, "final_run", boom)
    assert pt.smallmid_step(date(2027, 1, 15))["error"] == "RuntimeError: sin red"


def test_status_without_cache_never_initializes_or_downloads(pt, monkeypatch):
    monkeypatch.setattr(pt, "live_symbols", pt.store.live_symbols)
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("No writable SQLite connection"))
    monkeypatch.setattr("requests.sessions.Session.request", lambda *a, **k: pytest.fail("No network"))
    before = set(config.DATA_DIR.rglob("*"))
    report = pt.status(AFTER_CLOSE)
    assert set(config.DATA_DIR.rglob("*")) == before
    assert report["precios"] == {"SPY": None, "RSP": None}
    assert report["universo_sin_ultimo_cierre"] == 1.0
    assert not report["precios_al_dia"] and report["pruebas_ciegas"] == []


def test_broken_blind_chain_blocks_even_with_fresh_prices(pt, monkeypatch):
    _seed("2024-01-10")
    calls = _calls(monkeypatch)
    monkeypatch.setattr(pt.blind, "list_status", lambda: {"items": [{
        "id": 7, "name": "Broken", "status": "locked", "next_rebalance_due": "2024-01-10",
        "integrity": {"ok": False}, "n_periods": 1}]})
    assert pt.record_due(AFTER_CLOSE) == [{"id": 7, "registrado": False, "motivo": "cadena de hashes rota; revisar"}]
    assert calls == []


def test_tiingo_failure_releases_lock_without_freezing_data(pt, monkeypatch):
    pt.store.queue_path.parent.mkdir(parents=True)
    pt.store.queue_path.write_text("ABC")
    monkeypatch.setattr(pt.operations, "fetch_tiingo", lambda symbols: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(pt.operations, "mark_tiingo_complete", lambda result: pytest.fail("Do not freeze after failure"))
    with pytest.raises(RuntimeError, match="offline"):
        pt.resume_tiingo()
    assert not pt.store.lock_path.exists() and not pt.store.log_path.exists()


def test_tiingo_lock_is_exclusive(pt):
    assert pt.store.acquire_tiingo(AFTER_CLOSE) is None
    assert "en curso" in pt.store.acquire_tiingo(AFTER_CLOSE)
    pt.store.release_tiingo()
    assert pt.store.acquire_tiingo(AFTER_CLOSE) is None
    pt.store.release_tiingo()


def test_freshness_tolerance_preserves_missing_and_future_prices():
    from gabi.domain.market.freshness import maintenance_freshness

    symbols = [f"A{i}" for i in range(20)]
    prices = dict.fromkeys([*symbols, "SPY", "RSP"], "2024-01-10")
    prices["A0"] = None
    assert maintenance_freshness(symbols, prices, "2024-01-10")[1:] == (.05, True)
    prices["A1"] = "2024-01-09"
    assert maintenance_freshness(symbols, prices, "2024-01-10")[1:] == (.1, False)
    prices["A0"] = prices["A1"] = "2024-01-11"
    assert maintenance_freshness(symbols, prices, "2024-01-10")[1:] == (0, True)
    prices["RSP"] = "2024-01-11"
    assert not maintenance_freshness(symbols, prices, "2024-01-10")[2]


def test_status_uses_one_bounded_price_read(pt, monkeypatch):
    _seed("2024-01-10")
    calls = []
    read = pt.store.latest_prices
    monkeypatch.setattr(pt.store, "latest_prices", lambda symbols: calls.append(symbols) or read(symbols))
    report = pt.status(AFTER_CLOSE)
    assert report["precios_al_dia"] and calls == [["A", "SPY", "RSP"]]


def test_maintenance_refuses_mismatched_legacy_data_dir(tmp_path):
    with pytest.raises(ValueError, match="mismo directorio"):
        build_periodic_tasks(tmp_path)
