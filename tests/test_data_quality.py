import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import config, data_quality, edgar, entity_master, insider, macro, scoring, storage


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
    result = data_quality.universe_summary([])
    assert result["n_symbols"] == 0
    assert result["sources"] == {}


def test_universe_summary_price_coverage_and_freshness(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    today = pd.Timestamp.now(tz="UTC").normalize()
    storage.upsert_prices("FRESH", _price_df(today.strftime("%Y-%m-%d")))
    storage.upsert_prices("STALE", _price_df((today - pd.Timedelta(days=60)).strftime("%Y-%m-%d")))

    summary = data_quality.universe_summary(["FRESH", "STALE", "NODATA"])
    prices = summary["sources"]["prices"]
    assert prices["coverage"] == 2 / 3  # FRESH y STALE tienen precio, NODATA no
    assert prices["fresh"] == 1 / 3  # solo FRESH está dentro del umbral


def test_universe_summary_fundamentals_and_edgar_freshness(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    storage.upsert_fundamentals("AAA", {"sector": "Tech"}, None, None)
    edgar.upsert_edgar_metrics("AAA", "0000000001", {"roic": 0.2, "latest_10k_date": "2024-01-01"})

    summary = data_quality.universe_summary(["AAA", "BBB"])
    assert summary["sources"]["fundamentals"]["coverage"] == 0.5
    assert summary["sources"]["fundamentals"]["fresh"] == 0.5  # recién insertado
    assert summary["sources"]["edgar"]["coverage"] == 0.5
    assert summary["sources"]["edgar"]["with_facts_pct"] == 0.0  # sin edgar_facts, solo edgar_metrics


def test_universe_summary_insider_and_macro(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    insider.upsert_insider_transactions("AAA", [])
    macro.upsert_series("DGS10", [])

    summary = data_quality.universe_summary(["AAA", "BBB"])
    assert summary["sources"]["insider"]["coverage"] == 0.5
    assert summary["macro"]["n_series"] == 1
    assert summary["macro"]["oldest_hours"] < 1.0


def test_universe_summary_cik_status_none_without_local_cache(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    # CIK_CACHE se fija en edgar.py al importar el módulo (Path calculado una
    # vez a partir de config.DATA_DIR de entonces) -- monkeypatchear
    # config.DATA_DIR no lo mueve, hay que apuntar el propio atributo.
    monkeypatch.setattr(edgar, "CIK_CACHE", tmp_path / "sec_cik_map.csv")
    summary = data_quality.universe_summary(["AAA"])
    assert summary["cik"] is None  # sin sec_cik_map.csv en caché, no se dispara red


def test_symbol_provenance_reports_all_sources(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    storage.upsert_prices("AAA", _price_df("2024-01-05"))
    storage.upsert_fundamentals("AAA", {}, None, None)
    edgar.upsert_edgar_metrics("AAA", "0000000001", {"latest_10k_date": "2023-11-01", "latest_10q_date": "2024-08-01"})
    insider.upsert_insider_transactions("AAA", [])

    prov = data_quality.symbol_provenance("AAA")
    assert prov["prices"]["latest_date"] == "2024-01-05"
    assert prov["prices"]["age_hours"] is not None  # fecha fija en el pasado -> siempre stale en el test
    assert prov["prices"]["threshold_hours"] == data_quality.PRICE_STALE_DAYS * 24
    assert prov["fundamentals"]["age_hours"] < 1.0
    assert prov["fundamentals"]["threshold_hours"] == config.CACHE_MAX_AGE_HOURS
    assert prov["edgar"]["latest_10k_date"] == "2023-11-01"
    assert prov["edgar"]["latest_10q_date"] == "2024-08-01"
    assert prov["edgar"]["has_facts"] is False
    assert prov["insider"]["age_hours"] < 1.0


def test_symbol_provenance_missing_data_returns_none_not_crash(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    prov = data_quality.symbol_provenance("NUNCA_DESCARGADO")
    assert prov["prices"]["latest_date"] is None
    assert prov["prices"]["age_hours"] is None
    assert prov["fundamentals"]["fetched_at"] is None
    assert prov["fundamentals"]["age_hours"] is None
    assert prov["edgar"]["fetched_at"] is None
    assert prov["edgar"]["has_facts"] is False
    assert prov["insider"]["fetched_at"] is None


def test_age_hours_handles_none_and_aware_datetime():
    assert data_quality._age_hours(None) is None
    aware = datetime.now(UTC) - timedelta(hours=2)
    age = data_quality._age_hours(aware)
    assert 1.9 < age < 2.1


def test_universe_summary_entity_master_distinguishes_exact_approximate_and_missing(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    today = pd.Timestamp.now(tz="UTC").date().isoformat()
    # EXACTA: foto de hace más de 1 año -- point-in-time real para la fecha
    # de referencia (hace 1 año) que usa universe_summary.
    entity_master.record_snapshot(
        pd.DataFrame({"symbol": ["EXACTA"], "name": ["Exacta Inc"], "sector": ["Tech"], "industry": ["SW"]}),
        effective_date="2020-01-01",
    )
    # APROX: solo tiene una foto MUY RECIENTE (de hoy) -- para la fecha de
    # referencia de hace 1 año, cae al fallback (aproximación).
    entity_master.record_snapshot(
        pd.DataFrame({"symbol": ["APROX"], "name": ["Aprox Inc"], "sector": ["Health"], "industry": ["Bio"]}),
        effective_date=today,
    )
    # SINFOTO: nunca se le tomó ninguna foto.

    summary = data_quality.universe_summary(["EXACTA", "APROX", "SINFOTO"])
    em = summary["sources"]["entity_master"]
    assert em["coverage"] == pytest.approx(2 / 3)  # EXACTA y APROX tienen alguna foto
    assert em["fresh"] == pytest.approx(1 / 3)  # solo EXACTA es point-in-time real para la referencia pasada


def test_symbol_provenance_includes_entity_master_status(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    entity_master.record_snapshot(
        pd.DataFrame({"symbol": ["AAA"], "name": ["Acme"], "sector": ["Tech"], "industry": ["SW"]}),
        effective_date=pd.Timestamp.now(tz="UTC").date().isoformat(),  # foto de HOY
    )

    prov = data_quality.symbol_provenance("AAA")
    assert prov["entity_master"]["sector"] == "Tech"
    assert prov["entity_master"]["has_snapshot"] is True
    # Solo hay foto de hoy -- para la fecha de referencia (hace 1 año), es aproximación.
    assert prov["entity_master"]["is_approximate"] is True

    prov_missing = data_quality.symbol_provenance("NUNCA_DESCARGADO")
    assert prov_missing["entity_master"]["has_snapshot"] is False
    assert prov_missing["entity_master"]["sector"] is None


def _scored_df(rows: dict) -> pd.DataFrame:
    """rows: {symbol: {"pe_pct": .., "pb_pct": .., ...}} -- simula la salida
    de scoring.build_scores sin tener que montar todo el pipeline."""
    return pd.DataFrame.from_dict(rows, orient="index")


def test_score_block_coverage_distinguishes_complete_partial_and_none():
    value_cols = [f"{c}_pct" for c in scoring.SCORE_METRICS["value"]]  # pe, pb, ev_ebitda
    df = _scored_df({
        "COMPLETA": dict.fromkeys(value_cols, 80.0),
        "PARCIAL": {value_cols[0]: 50.0, **{c: np.nan for c in value_cols[1:]}},
        "SINDATO": dict.fromkeys(value_cols, np.nan),
    })
    coverage = data_quality.score_block_coverage(df)
    assert coverage["value"]["complete"] == pytest.approx(1 / 3)
    assert coverage["value"]["any"] == pytest.approx(2 / 3)
    assert coverage["value"]["none"] == pytest.approx(1 / 3)


def test_score_block_coverage_empty_df_and_missing_columns():
    assert data_quality.score_block_coverage(pd.DataFrame())["value"]["none"] == 0.0
    # df sin ninguna columna _pct del bloque -> como si nadie tuviera dato.
    df = pd.DataFrame({"otra_columna": [1, 2]})
    result = data_quality.score_block_coverage(df)
    assert result["value"]["complete"] == 0.0
    assert result["value"]["none"] == 1.0


def test_recent_errors_summary_delegates_to_storage(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    storage.record_update_errors("yahoo_precio", {"AAA": "timeout"})
    errors = data_quality.recent_errors_summary()
    assert len(errors) == 1
    assert errors.iloc[0]["symbol"] == "AAA"


def test_compute_data_fingerprint_is_deterministic_and_order_independent(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    storage.upsert_prices("AAA", _price_df("2024-01-05"))
    storage.upsert_prices("BBB", _price_df("2024-01-05"))

    fp1 = data_quality.compute_data_fingerprint(["AAA", "BBB"])
    fp2 = data_quality.compute_data_fingerprint(["BBB", "AAA"])  # orden distinto
    assert fp1 == fp2
    assert fp1 == data_quality.compute_data_fingerprint(["AAA", "BBB"])  # repetible


def test_compute_data_fingerprint_changes_when_underlying_data_changes(tmp_path, monkeypatch):
    _set_db(tmp_path, monkeypatch)
    storage.upsert_prices("AAA", _price_df("2024-01-05"))
    before = data_quality.compute_data_fingerprint(["AAA"])

    storage.upsert_prices("AAA", _price_df("2024-01-08"))  # nueva sesión de precio
    after = data_quality.compute_data_fingerprint(["AAA"])

    assert before != after


def test_compute_data_fingerprint_empty_symbols_is_stable():
    assert data_quality.compute_data_fingerprint([]) == data_quality.compute_data_fingerprint([])


def test_block_coverage_warnings_flags_only_blocks_below_threshold():
    coverage = {
        "value": {"complete": 0.95, "any": 1.0, "none": 0.0, "n_metrics": 3},
        "quality": {"complete": 0.40, "any": 0.90, "none": 0.05, "n_metrics": 4},
    }
    warnings = data_quality.block_coverage_warnings(coverage, threshold=0.70)
    assert len(warnings) == 1
    assert "Quality" in warnings[0]
    assert "40%" in warnings[0]


def test_block_coverage_warnings_empty_when_all_above_threshold():
    coverage = {"value": {"complete": 0.95, "any": 1.0, "none": 0.0, "n_metrics": 3}}
    assert data_quality.block_coverage_warnings(coverage, threshold=0.70) == []


def test_low_confidence_candidates_flags_only_symbols_below_threshold():
    df = pd.DataFrame({
        "confidence": [80.0, 40.0, np.nan],
        "score_coverage": [0.9, 0.3, 0.1],
    }, index=["ALTA", "BAJA", "SINDATO"])
    result = data_quality.low_confidence_candidates(df, ["ALTA", "BAJA", "SINDATO", "NOESTA"], threshold=60.0)
    assert len(result) == 1
    assert result[0]["symbol"] == "BAJA"
    assert result[0]["confidence"] == 40.0
    assert result[0]["score_coverage"] == 0.3


def test_low_confidence_candidates_without_confidence_column_returns_empty():
    df = pd.DataFrame({"other": [1, 2]}, index=["AAA", "BBB"])
    assert data_quality.low_confidence_candidates(df, ["AAA"]) == []
