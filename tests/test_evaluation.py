import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, evaluation, storage


def _seed(symbol, p0, p1):
    df = pd.DataFrame({
        "Open": [p0, p1], "High": [p0, p1], "Low": [p0, p1],
        "Close": [p0, p1], "Adj Close": [p0, p1], "Volume": [100, 100],
    }, index=pd.to_datetime(["2024-01-02", "2024-07-02"]))
    storage.upsert_prices(symbol, df)


def _seed_to_today(symbol, p_start, p_today, start_date):
    df = pd.DataFrame({
        "Open": [p_start, p_today], "High": [p_start, p_today], "Low": [p_start, p_today],
        "Close": [p_start, p_today], "Adj Close": [p_start, p_today], "Volume": [100, 100],
    }, index=pd.to_datetime([start_date, date.today().isoformat()]))
    storage.upsert_prices(symbol, df)


def test_snapshot_and_evaluation_expose_missing_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    table = pd.DataFrame({"composite_score": [80., 70., float("nan")],
                          "score_coverage": [.9, .8, .2]}, index=["AAA", "BBB", "CCC"])
    snapshot = evaluation.save_snapshot(table, "2024-01-02")
    assert evaluation.snapshot_symbols(snapshot) == ["AAA", "BBB"]
    _seed("AAA", 100, 120)
    _seed("SPY", 100, 110)
    result = evaluation.evaluate(["AAA", "BBB"], "2024-01-02", 6, cost_bps=10)
    assert result["status"] == "incomplete"
    assert result["missing"] == ["BBB"]
    assert round(result["portfolio_return"], 3) == .198
    assert round(result["benchmark_return"], 3) == .098


def test_snapshot_default_name_uses_date(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    table = pd.DataFrame({"composite_score": [80.], "score_coverage": [.9]}, index=["AAA"])
    evaluation.save_snapshot(table, "2024-01-02")
    row = evaluation.list_snapshots().iloc[0]
    assert row["name"] == "Ranking 2024-01-02"


def test_snapshot_custom_name_and_rename(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    table = pd.DataFrame({"composite_score": [80.], "score_coverage": [.9]}, index=["AAA"])
    snapshot = evaluation.save_snapshot(table, "2024-01-02", name="Pesos antes del cambio")
    row = evaluation.list_snapshots().iloc[0]
    assert row["name"] == "Pesos antes del cambio"

    assert evaluation.rename_snapshot(snapshot, "Pesos después del cambio")
    row = evaluation.list_snapshots().iloc[0]
    assert row["name"] == "Pesos después del cambio"
    # renombrar no debe duplicar filas (el nombre se guarda por candidata)
    assert len(evaluation.list_snapshots()) == 1


def test_rename_snapshot_rejects_invalid_name(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    table = pd.DataFrame({"composite_score": [80.], "score_coverage": [.9]}, index=["AAA"])
    snapshot = evaluation.save_snapshot(table, "2024-01-02")
    try:
        evaluation.rename_snapshot(snapshot, "   ")
        assert False, "debia rechazar un nombre vacio"
    except ValueError:
        pass


def test_snapshot_progress_computes_return_up_to_today(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    start_date = "2024-01-02"
    table = pd.DataFrame({"composite_score": [80., 70.], "score_coverage": [.9, .8]}, index=["AAA", "BBB"])
    snapshot = evaluation.save_snapshot(table, start_date, top_n=2)
    _seed_to_today("AAA", 100, 150, start_date)  # +50%
    _seed_to_today("BBB", 100, 100, start_date)  # +0%
    _seed_to_today("SPY", 100, 120, start_date)  # +20%

    result = evaluation.snapshot_progress(snapshot)
    assert result["available"] == 2
    assert result["requested"] == 2
    assert round(result["portfolio_return"], 3) == .25  # media de +50% y 0%
    assert round(result["benchmark_return"], 3) == .20
    assert round(result["excess_return"], 3) == .05
    assert len(result["detail"]) == 2  # solo las 2 candidatas guardadas, ni una mas
    assert set(result["detail"]["symbol"]) == {"AAA", "BBB"}


def test_snapshot_progress_reports_missing_prices_without_treating_as_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    start_date = "2024-01-02"
    table = pd.DataFrame({"composite_score": [80., 70.], "score_coverage": [.9, .8]}, index=["AAA", "BBB"])
    snapshot = evaluation.save_snapshot(table, start_date, top_n=2)
    _seed_to_today("AAA", 100, 150, start_date)
    _seed_to_today("SPY", 100, 120, start_date)

    result = evaluation.snapshot_progress(snapshot)
    assert result["available"] == 1
    assert result["missing"] == ["BBB"]
    assert round(result["portfolio_return"], 3) == .5  # solo cuenta AAA, BBB no se trata como 0


def test_snapshot_progress_flags_stale_cache_without_newer_data(tmp_path, monkeypatch):
    """Si el precio cacheado mas reciente es de la MISMA fecha (o anterior) a
    cuando se guardo el ranking, no hay ningun dia nuevo que comparar todavia
    -- debe marcarse como 'stale', no como '0% de cambio real'. Se guarda el
    ranking a fecha de HOY para que "el unico precio cacheado es el mismo
    dia" sea un caso real, no un artefacto de estar fuera de la ventana de
    tolerancia de 7 dias que usa _adjusted_at."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    start_date = date.today().isoformat()
    table = pd.DataFrame({"composite_score": [80.], "score_coverage": [.9]}, index=["AAA"])
    snapshot = evaluation.save_snapshot(table, start_date, top_n=1)
    # unico precio cacheado: la propia fecha del snapshot, nada posterior
    df = pd.DataFrame({"Open": [100], "High": [100], "Low": [100], "Close": [100],
                       "Adj Close": [100], "Volume": [100]}, index=pd.to_datetime([start_date]))
    storage.upsert_prices("AAA", df)
    storage.upsert_prices("SPY", df)

    result = evaluation.snapshot_progress(snapshot)
    assert result["stale"] is True
    assert result["data_as_of"] == start_date
    assert result["portfolio_return"] == 0.0  # matematicamente correcto, pero "stale" avisa de por que


def test_snapshot_created_at_includes_madrid_time(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    table = pd.DataFrame({"composite_score": [80.], "score_coverage": [.9]}, index=["AAA"])
    evaluation.save_snapshot(table, "2024-01-02")
    row = evaluation.list_snapshots().iloc[0]
    # ISO con hora y offset (+01:00 / +02:00 segun horario de verano), no solo fecha
    assert "T" in row["created_at"]
    assert row["created_at"][:10] == date.today().isoformat()


def test_snapshot_price_curve_normalizes_to_100_at_start(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    start_date = "2024-01-02"
    table = pd.DataFrame({"composite_score": [80.], "score_coverage": [.9]}, index=["AAA"])
    snapshot = evaluation.save_snapshot(table, start_date, top_n=1)
    _seed_to_today("AAA", 100, 200, start_date)  # se duplica
    _seed_to_today("SPY", 50, 55, start_date)  # +10%

    curve = evaluation.snapshot_price_curve(snapshot)
    assert curve.iloc[0]["Cartera"] == 100
    assert curve.iloc[0]["SPY"] == 100
    assert round(curve.iloc[-1]["Cartera"], 1) == 200.0
    assert round(curve.iloc[-1]["SPY"], 1) == 110.0
