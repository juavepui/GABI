"""Blind validation ledger: immutable sealed periods, explicit writes and read-only reads."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS blind_validations (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    model_id TEXT NOT NULL,
    weights_json TEXT NOT NULL,
    n_positions INTEGER NOT NULL,
    rebalance_months INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    unlock_date TEXT NOT NULL,
    git_commit_created TEXT,
    status TEXT NOT NULL DEFAULT 'locked',
    broken_early_at TEXT,
    broken_early_reason TEXT
);
CREATE TABLE IF NOT EXISTS blind_validation_periods (
    id INTEGER PRIMARY KEY,
    validation_id INTEGER NOT NULL,
    rebalance_date TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    symbols_json TEXT NOT NULL,
    weights_json TEXT NOT NULL,
    entry_prices_json TEXT NOT NULL,
    git_commit TEXT,
    prev_hash TEXT,
    record_hash TEXT NOT NULL,
    UNIQUE(validation_id, rebalance_date)
);
-- Opcional por validación (#43): puntuación completa del universo en cada
-- rebalanceo, para medir el IC de sección cruzada de forma prospectiva. Tabla
-- aparte: no altera los periodos ni la cadena de hashes existentes.
CREATE TABLE IF NOT EXISTS blind_validation_options (
    validation_id INTEGER PRIMARY KEY,
    store_ranking INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS blind_validation_rankings (
    validation_id INTEGER NOT NULL,
    rebalance_date TEXT NOT NULL,
    ranking_json TEXT NOT NULL,
    ranking_hash TEXT NOT NULL,
    PRIMARY KEY(validation_id, rebalance_date)
);
"""
VALIDATION_COLUMNS = ("id", "created_at", "name", "model_id", "weights_json", "n_positions", "rebalance_months",
                      "start_date", "unlock_date", "git_commit_created", "status", "broken_early_at",
                      "broken_early_reason")


class DuplicatePeriod(Exception):
    """A sealed rebalance already exists for this validation and date."""


def _rows(conn, query, params=()) -> list[dict]:
    cursor = conn.execute(query, params)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


class SqliteBlindLedger:
    def __init__(self, path: Path):
        self.path = path

    def _write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        return closing(conn)

    def _read(self, action, absent):
        if not self.path.is_file():
            return absent
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)) as conn:
            conn.execute("PRAGMA query_only=ON")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            if not {"blind_validations", "blind_validation_periods"} <= tables:
                return absent
            return action(conn)

    def create(self, record: dict) -> int:
        with self._write() as conn:
            cursor = conn.execute(
                "INSERT INTO blind_validations (created_at, name, model_id, weights_json, n_positions, "
                "rebalance_months, start_date, unlock_date, git_commit_created, status) "
                "VALUES (?,?,?,?,?,?,?,?,?,'locked')",
                (record["created_at"], record["name"], record["model_id"], record["weights_json"],
                 record["n_positions"], record["rebalance_months"], record["start_date"], record["unlock_date"],
                 record["git_commit_created"]))
            conn.commit()
            return cursor.lastrowid

    def validation(self, validation_id: int) -> dict:
        return self._read(lambda conn: next(iter(_rows(
            conn, "SELECT * FROM blind_validations WHERE id = ?", (validation_id,))), {}), {})

    def periods(self, validation_id: int) -> list[dict]:
        return self._read(lambda conn: _rows(
            conn, "SELECT * FROM blind_validation_periods WHERE validation_id = ? ORDER BY rebalance_date",
            (validation_id,)), [])

    def seal(self, period: dict, ranking: Callable[[], tuple[str, str]]) -> None:
        """Insert a period, and its full ranking when the validation stores one, in one transaction.

        ``ranking`` builds (json, sha256) only if the validation enabled snapshots."""
        with self._write() as conn:
            try:
                conn.execute(
                    "INSERT INTO blind_validation_periods (validation_id, rebalance_date, recorded_at, "
                    "symbols_json, weights_json, entry_prices_json, git_commit, prev_hash, record_hash) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    tuple(period[name] for name in ("validation_id", "rebalance_date", "recorded_at", "symbols_json",
                                                    "weights_json", "entry_prices_json", "git_commit", "prev_hash",
                                                    "record_hash")))
                if self._stores_ranking(conn, period["validation_id"]):
                    conn.execute("INSERT INTO blind_validation_rankings VALUES (?,?,?,?)",
                                 (period["validation_id"], period["rebalance_date"], *ranking()))
                conn.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise DuplicatePeriod(str(exc)) from exc
                raise

    @staticmethod
    def _stores_ranking(conn, validation_id: int) -> bool:
        row = conn.execute("SELECT store_ranking FROM blind_validation_options WHERE validation_id=?",
                           (validation_id,)).fetchone()
        return bool(row and row[0])

    def enable_ranking(self, validation_id: int) -> bool:
        """False when the validation does not exist; nothing is written then."""
        with self._write() as conn:
            if not conn.execute("SELECT 1 FROM blind_validations WHERE id = ?", (validation_id,)).fetchone():
                return False
            conn.execute("INSERT OR REPLACE INTO blind_validation_options VALUES (?,1)", (validation_id,))
            conn.commit()
            return True

    def break_seal(self, validation_id: int, at: str, reason: str) -> None:
        with self._write() as conn:
            conn.execute("UPDATE blind_validations SET status='broken_early', broken_early_at=?, "
                         "broken_early_reason=? WHERE id = ?", (at, reason, validation_id))
            conn.commit()

    def validations(self) -> pd.DataFrame:
        return self._read(lambda conn: pd.read_sql_query("SELECT * FROM blind_validations ORDER BY id DESC", conn),
                          pd.DataFrame(columns=list(VALIDATION_COLUMNS)))
