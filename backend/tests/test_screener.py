import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import screener


def test_get_universe_records_entity_snapshot_only_on_force_refresh(monkeypatch):
    uni = pd.DataFrame([{"symbol": "AAA", "name": "Empresa A", "sector": "Tech", "industry": "Software"}])
    monkeypatch.setattr(screener.universe, "get_sp500_constituents", lambda force_refresh=False: uni)
    calls = []
    monkeypatch.setattr(screener.entity_master, "record_snapshot", lambda df, effective_date=None: calls.append(df))

    screener.get_universe(force_refresh=False)
    assert calls == []  # una simple lectura cacheada no debe escribir una foto nueva

    screener.get_universe(force_refresh=True)
    assert len(calls) == 1
    pd.testing.assert_frame_equal(calls[0], uni)
