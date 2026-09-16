import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import edgar


def _isolate_db(tmp_path, monkeypatch):
    from gabi import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")


def test_ensure_edgar_data_refetches_fresh_symbol_without_raw_facts(tmp_path, monkeypatch):
    # Reproduce exactamente el bug real encontrado al ejecutar el backtest
    # multifactor: un símbolo cacheado ANTES de que existiera edgar_facts
    # (o al que se le perdió por cualquier motivo) tiene un fetched_at de
    # hace un minuto -> "fresco" por fecha, pero sin ninguna fila en
    # edgar_facts. Sin el chequeo de get_symbols_with_facts, ensure_edgar_data
    # lo daría por bueno para siempre y el ranking histórico nunca tendría
    # sus fundamentales, aunque el símbolo "ya se hubiera actualizado".
    _isolate_db(tmp_path, monkeypatch)

    edgar.upsert_edgar_metrics("AAA", "0000000001", {
        "revenue_cagr_3y": 0.1, "fcf_cagr_3y": 0.1, "roic": 0.1,
        "latest_10k_date": None, "latest_10k_url": None,
        "latest_10q_date": None, "latest_10q_url": None,
    })
    assert edgar.get_symbols_with_facts(["AAA"]) == set()  # confirma el escenario del bug

    calls = []

    def fake_get_cik_map(force_refresh=False):
        return pd.DataFrame([{"symbol": "AAA", "cik": "0000000001", "title": "Acme Corp"}])

    def fake_fetch_edgar_batch(symbols, cik_by_symbol, max_workers=4, progress_cb=None):
        calls.append(list(symbols))
        return {}

    monkeypatch.setattr(edgar, "get_cik_map", fake_get_cik_map)
    monkeypatch.setattr(edgar, "fetch_edgar_batch", fake_fetch_edgar_batch)

    result = edgar.ensure_edgar_data(["AAA"])
    assert calls == [["AAA"]]  # se reintentó aunque fetched_at fuera reciente
    assert result["edgar_refreshed"] == 1


def test_ensure_edgar_data_skips_symbol_that_already_has_facts(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)

    edgar.upsert_edgar_metrics("AAA", "0000000001", {
        "revenue_cagr_3y": 0.1, "fcf_cagr_3y": 0.1, "roic": 0.1,
        "latest_10k_date": None, "latest_10k_url": None,
        "latest_10q_date": None, "latest_10q_url": None,
    })
    edgar.upsert_edgar_facts("AAA", [{
        "tag": "Revenues", "unit": "USD", "start_date": "2018-01-01", "end_date": "2018-12-31",
        "val": 100.0, "form": "10-K", "fp": "FY", "fy": 2018, "filed_date": "2019-02-01", "accn": "a1",
    }])

    def fake_get_cik_map(force_refresh=False):
        return pd.DataFrame([{"symbol": "AAA", "cik": "0000000001", "title": "Acme Corp"}])

    def fail_if_called(*args, **kwargs):
        raise AssertionError("no debería re-descargar un símbolo fresco que ya tiene edgar_facts")

    monkeypatch.setattr(edgar, "get_cik_map", fake_get_cik_map)
    monkeypatch.setattr(edgar, "fetch_edgar_batch", fail_if_called)

    result = edgar.ensure_edgar_data(["AAA"])
    assert result["edgar_refreshed"] == 0
