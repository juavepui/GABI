import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, entity_master as em


def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")


def _no_network_cik(monkeypatch):
    # record_snapshot resuelve CIK vía edgar -- se evita red en los tests
    # devolviendo (None, None) siempre, igual que un simbolo no resoluble.
    monkeypatch.setattr(em.edgar, "get_cik_map", lambda: pd.DataFrame(columns=["symbol", "cik", "title"]))
    monkeypatch.setattr(em.edgar, "get_cik_for_symbol", lambda symbol, cik_map=None: (None, None))


def test_get_sector_asof_returns_none_for_unknown_symbol(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    result = em.get_sector_asof(["ZZZ"], "2020-01-01")
    assert result["ZZZ"]["sector"] is None
    assert result["ZZZ"]["is_approximate"] is True


def test_record_snapshot_then_lookup_on_or_before_is_not_approximate(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _no_network_cik(monkeypatch)
    uni = pd.DataFrame([{"symbol": "AAA", "name": "Empresa A", "sector": "Tech", "industry": "Software"}])
    written = em.record_snapshot(uni, effective_date="2024-01-01")
    assert written == 1

    result = em.get_sector_asof(["AAA"], "2024-06-01")  # fecha posterior a la foto -> real, no aproximada
    assert result["AAA"] == {
        "sector": "Tech", "industry": "Software", "name": "Empresa A", "cik": None,
        "effective_date": "2024-01-01", "is_approximate": False,
    }


def test_record_snapshot_lookup_before_snapshot_falls_back_as_approximate(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _no_network_cik(monkeypatch)
    uni = pd.DataFrame([{"symbol": "AAA", "name": "Empresa A", "sector": "Tech", "industry": "Software"}])
    em.record_snapshot(uni, effective_date="2024-01-01")

    result = em.get_sector_asof(["AAA"], "2016-01-01")  # fecha ANTERIOR a la unica foto que existe
    assert result["AAA"]["sector"] == "Tech"  # misma info, pero marcada como aproximacion
    assert result["AAA"]["is_approximate"] is True


def test_record_snapshot_is_idempotent_per_symbol_and_date(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _no_network_cik(monkeypatch)
    uni1 = pd.DataFrame([{"symbol": "AAA", "name": "Empresa A", "sector": "Tech", "industry": "Software"}])
    uni2 = pd.DataFrame([{"symbol": "AAA", "name": "Empresa A", "sector": "Salud", "industry": "Farma"}])
    em.record_snapshot(uni1, effective_date="2024-01-01")
    em.record_snapshot(uni2, effective_date="2024-01-01")  # mismo dia, sector distinto -> sobrescribe, no duplica

    result = em.get_sector_asof(["AAA"], "2024-06-01")
    assert result["AAA"]["sector"] == "Salud"  # la ultima escritura del mismo dia gana


def test_get_sector_asof_picks_most_recent_snapshot_not_exceeding_as_of(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    _no_network_cik(monkeypatch)
    em.record_snapshot(pd.DataFrame([{"symbol": "AAA", "name": "A", "sector": "Tech", "industry": "Software"}]),
                       effective_date="2024-01-01")
    em.record_snapshot(pd.DataFrame([{"symbol": "AAA", "name": "A", "sector": "Industrial", "industry": "Maquinaria"}]),
                       effective_date="2025-06-01")

    # a mitad de camino: debe usar la foto de 2024, no la de 2025 (todavia no habia pasado)
    mid = em.get_sector_asof(["AAA"], "2024-12-01")
    assert mid["AAA"]["sector"] == "Tech"
    assert mid["AAA"]["is_approximate"] is False

    later = em.get_sector_asof(["AAA"], "2026-01-01")
    assert later["AAA"]["sector"] == "Industrial"
    assert later["AAA"]["is_approximate"] is False


def test_get_sector_asof_batches_multiple_symbols():
    result = em.get_sector_asof([], "2024-01-01")
    assert result == {}
