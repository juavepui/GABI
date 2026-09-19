"""Verifica que abrir una base de datos con el esquema ANTIGUO (creada por
una versión previa del código, sin las columnas que se añadieron después)
con el código ACTUAL no rompe ni pierde datos -- solo migra en silencio,
vía los `ALTER TABLE ADD COLUMN` que ya existían dispersos por el proyecto
(storage.py, decision_engine.py, evaluation.py, research_lab.py,
sim_portfolios.py). Cada test construye la tabla tal y como la habría
dejado la versión de código anterior a esa columna, inserta una fila con
esas columnas antiguas, y comprueba que la función pública real (no la
privada de migración) la abre sin excepción, con el dato antiguo intacto y
la columna nueva ya disponible. Todo en SQLite local -- sin red."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import config, decision_engine, evaluation, research_lab, sim_portfolios, storage


def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")


def _raw_connection():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(config.DB_PATH)


def test_storage_migrates_prices_table_without_adj_close(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    with _raw_connection() as conn:
        conn.execute(
            "CREATE TABLE prices (symbol TEXT NOT NULL, date TEXT NOT NULL, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL, "
            "PRIMARY KEY (symbol, date))"
        )
        conn.execute("INSERT INTO prices VALUES ('AAA', '2024-01-02', 10, 11, 9, 10.5, 1000)")
        conn.commit()

    df = storage.get_prices("AAA")  # función pública real, no la privada de migración

    assert "adj_close" in df.columns
    assert df.loc["2024-01-02", "close"] == 10.5  # el dato antiguo sigue intacto
    assert df["adj_close"].isna().all()  # nueva columna, sin dato retroactivo -- NULL, no un valor inventado


def test_decision_engine_migrates_runs_table_without_name(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    with _raw_connection() as conn:
        conn.execute(
            "CREATE TABLE decision_runs (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, "
            "method TEXT NOT NULL, decisions_json TEXT NOT NULL, policy_json TEXT NOT NULL, "
            "holdings_json TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO decision_runs (id, created_at, method, decisions_json, policy_json, holdings_json) "
            "VALUES (1, '2024-01-02T10:00:00', 'min_variance', '{}', '{}', '{}')"
        )
        conn.commit()

    plans = decision_engine.list_saved_plans()

    assert len(plans) == 1
    assert plans.iloc[0]["method"] == "min_variance"  # dato antiguo intacto
    assert plans.iloc[0]["name"] == "Plan #1"  # backfill documentado para filas sin nombre


def test_evaluation_migrates_snapshots_table_without_name(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    with _raw_connection() as conn:
        conn.execute(
            "CREATE TABLE ranking_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "snapshot_id INTEGER NOT NULL, created_at TEXT NOT NULL, as_of_date TEXT NOT NULL, "
            "source TEXT NOT NULL, symbol TEXT NOT NULL, rank INTEGER NOT NULL, "
            "score REAL NOT NULL, coverage REAL NOT NULL)"
        )
        conn.execute(
            "INSERT INTO ranking_snapshots (snapshot_id, created_at, as_of_date, source, symbol, rank, "
            "score, coverage) VALUES (1, '2024-01-02T10:00:00', '2024-01-02', 'live', 'AAA', 1, 90.0, 1.0)"
        )
        conn.commit()

    snapshots = evaluation.list_snapshots()

    assert len(snapshots) == 1
    assert snapshots.iloc[0]["source"] == "live"  # dato antiguo intacto
    assert snapshots.iloc[0]["name"] == "Ranking 2024-01-02"  # backfill documentado


def test_research_lab_migrates_experiments_table_without_new_columns(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    with _raw_connection() as conn:
        conn.execute(
            "CREATE TABLE experiments (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, "
            "model_id TEXT NOT NULL, git_commit TEXT, hypothesis_registered INTEGER NOT NULL, "
            "stage TEXT NOT NULL, sharpe REAL)"
        )
        conn.execute(
            "INSERT INTO experiments (created_at, model_id, git_commit, hypothesis_registered, stage, sharpe) "
            "VALUES ('2024-01-02T10:00:00', 'GABI-MF-v0', 'old1234', 1, 'RESEARCH', 0.65)"
        )
        conn.commit()

    experiments = research_lab.list_experiments()

    assert len(experiments) == 1
    row = experiments.iloc[0]
    assert row["model_id"] == "GABI-MF-v0"  # dato antiguo intacto
    assert row["git_commit"] == "old1234"
    for col in ("deps_json", "python_version", "env_fingerprint"):
        assert col in experiments.columns
        assert row[col] is None  # columnas nuevas, sin dato retroactivo


def test_sim_portfolios_migrates_portfolios_and_trades_tables(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    with _raw_connection() as conn:
        conn.execute(
            "CREATE TABLE sim_portfolios (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, "
            "initial_cash REAL NOT NULL, stock_commission REAL NOT NULL, etf_commission REAL NOT NULL, "
            "spread_bps REAL NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE sim_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id INTEGER NOT NULL, "
            "symbol TEXT NOT NULL, asset_type TEXT NOT NULL, side TEXT NOT NULL, requested_date TEXT NOT NULL, "
            "execution_date TEXT NOT NULL, reference_close REAL NOT NULL, notional REAL NOT NULL, "
            "commission REAL NOT NULL, spread_bps REAL NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO sim_portfolios (id, name, initial_cash, stock_commission, etf_commission, "
            "spread_bps, created_at) VALUES (1, 'Cartera vieja', 10000, 1.0, 0.0, 10.0, '2024-01-02T10:00:00')"
        )
        conn.execute(
            "INSERT INTO sim_trades (portfolio_id, symbol, asset_type, side, requested_date, execution_date, "
            "reference_close, notional, commission, spread_bps, created_at) "
            "VALUES (1, 'AAA', 'stock', 'buy', '2024-01-02', '2024-01-02', 100.0, 1000.0, 1.0, 10.0, "
            "'2024-01-02T10:00:00')"
        )
        conn.commit()

    portfolios = sim_portfolios.list_portfolios()
    trades = sim_portfolios.list_trades(1)

    assert len(portfolios) == 1
    assert portfolios.iloc[0]["name"] == "Cartera vieja"  # dato antiguo intacto
    assert portfolios.iloc[0]["base_currency"] == "USD"  # columna nueva, con su DEFAULT aplicado

    assert len(trades) == 1
    assert trades.iloc[0]["symbol"] == "AAA"  # dato antiguo intacto
    assert trades.iloc[0]["market"] == "XNYS"  # columna nueva, con su DEFAULT aplicado
