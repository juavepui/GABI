import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import config, data_health, edgar, insider, macro, storage


def _set_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")


def _price_df(last_date: str, n: int = 3):
    dates = pd.date_range(end=last_date, periods=n, freq="B")
    closes = [100.0] * n
    return pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes,
         "Adj Close": closes, "Volume": [1] * n},
        index=dates,
    )


def test_universe_summary_empty_symbols():
    result = data_health.universe_summary([])
    assert result["n_symbols"] == 0
    assert result["sources"] == {}


def test_universe_summary_price_coverage_and_freshness(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    today = pd.Timestamp.now(tz="UTC").normalize()
    storage.upsert_prices("FRESH", _price_df(today.strftime("%Y-%m-%d")))
    storage.upsert_prices("STALE", _price_df((today - pd.Timedelta(days=60)).strftime("%Y-%m-%d")))

    summary = data_health.universe_summary(["FRESH", "STALE", "NODATA"])
    prices = summary["sources"]["prices"]
    assert prices["coverage"] == 2 / 3  # FRESH y STALE tienen precio, NODATA no
    assert prices["fresh"] == 1 / 3  # solo FRESH está dentro del umbral


def test_universe_summary_fundamentals_and_edgar_freshness(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    storage.upsert_fundamentals("AAA", {"sector": "Tech"}, None, None)
    edgar.upsert_edgar_metrics("AAA", "0000000001", {"roic": 0.2, "latest_10k_date": "2024-01-01"})

    summary = data_health.universe_summary(["AAA", "BBB"])
    assert summary["sources"]["fundamentals"]["coverage"] == 0.5
    assert summary["sources"]["fundamentals"]["fresh"] == 0.5  # recién insertado
    assert summary["sources"]["edgar"]["coverage"] == 0.5
    assert summary["sources"]["edgar"]["with_facts_pct"] == 0.0  # sin edgar_facts, solo edgar_metrics


def test_universe_summary_insider_and_macro(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    insider.upsert_insider_transactions("AAA", [])
    macro.upsert_series("DGS10", [])

    summary = data_health.universe_summary(["AAA", "BBB"])
    assert summary["sources"]["insider"]["coverage"] == 0.5
    assert summary["macro"]["n_series"] == 1
    assert summary["macro"]["oldest_hours"] < 1.0


def test_universe_summary_cik_status_none_without_local_cache(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    # CIK_CACHE se fija en edgar.py al importar el módulo (Path calculado una
    # vez a partir de config.DATA_DIR de entonces) -- monkeypatchear
    # config.DATA_DIR no lo mueve, hay que apuntar el propio atributo.
    monkeypatch.setattr(edgar, "CIK_CACHE", tmp_path / "sec_cik_map.csv")
    summary = data_health.universe_summary(["AAA"])
    assert summary["cik"] is None  # sin sec_cik_map.csv en caché, no se dispara red


def test_symbol_provenance_reports_all_sources(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    storage.upsert_prices("AAA", _price_df("2024-01-05"))
    storage.upsert_fundamentals("AAA", {}, None, None)
    edgar.upsert_edgar_metrics("AAA", "0000000001", {"latest_10k_date": "2023-11-01", "latest_10q_date": "2024-08-01"})
    insider.upsert_insider_transactions("AAA", [])

    prov = data_health.symbol_provenance("AAA")
    assert prov["prices"]["latest_date"] == "2024-01-05"
    assert prov["prices"]["age_hours"] is not None  # fecha fija en el pasado -> siempre stale en el test
    assert prov["prices"]["threshold_hours"] == data_health.PRICE_STALE_DAYS * 24
    assert prov["fundamentals"]["age_hours"] < 1.0
    assert prov["fundamentals"]["threshold_hours"] == config.CACHE_MAX_AGE_HOURS
    assert prov["edgar"]["latest_10k_date"] == "2023-11-01"
    assert prov["edgar"]["latest_10q_date"] == "2024-08-01"
    assert prov["edgar"]["has_facts"] is False
    assert prov["insider"]["age_hours"] < 1.0


def test_symbol_provenance_missing_data_returns_none_not_crash(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    prov = data_health.symbol_provenance("NUNCA_DESCARGADO")
    assert prov["prices"]["latest_date"] is None
    assert prov["prices"]["age_hours"] is None
    assert prov["fundamentals"]["fetched_at"] is None
    assert prov["fundamentals"]["age_hours"] is None
    assert prov["edgar"]["fetched_at"] is None
    assert prov["edgar"]["has_facts"] is False
    assert prov["insider"]["fetched_at"] is None


def test_age_hours_handles_none_and_aware_datetime():
    assert data_health._age_hours(None) is None
    aware = datetime.now(UTC) - timedelta(hours=2)
    age = data_health._age_hours(aware)
    assert 1.9 < age < 2.1
