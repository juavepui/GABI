"""Research Lab experiment log: explicit writes and read-only reads of the published ``experiments`` table."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    model_id TEXT NOT NULL,
    git_commit TEXT,
    data_cutoff TEXT,
    universe TEXT,
    factors TEXT,
    weights_json TEXT,
    n_positions INTEGER,
    rebalance TEXT,
    cost_model TEXT,
    is_start TEXT,
    is_end TEXT,
    oos_start TEXT,
    oos_end TEXT,
    hypothesis_registered INTEGER NOT NULL,
    stage TEXT NOT NULL,
    family TEXT,
    deps_json TEXT,
    python_version TEXT,
    env_fingerprint TEXT,
    data_fingerprint TEXT,
    sharpe REAL,
    sortino REAL,
    max_drawdown REAL,
    total_return REAL,
    annualized_return REAL,
    periods_per_year REAL,
    n_periods INTEGER,
    returns_json TEXT,
    notes TEXT,
    result_json TEXT
);
"""
# Columns added after the table was first published, in the order they were added.
LATE_COLUMNS = ("deps_json", "python_version", "env_fingerprint", "data_fingerprint")
COLUMNS = tuple(line.split()[0] for line in SCHEMA.strip().splitlines()[1:-1])
INSERTED = COLUMNS[1:]


def ensure_columns(conn: sqlite3.Connection) -> None:
    present = {row[1] for row in conn.execute("PRAGMA table_info(experiments)")}
    for column in LATE_COLUMNS:
        if column not in present:
            conn.execute(f"ALTER TABLE experiments ADD COLUMN {column} TEXT")


class SqliteExperimentLog:
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
            if not conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='experiments'").fetchone():
                return absent
            return action(conn)

    def record(self, values: dict) -> int:
        with self._write() as conn:
            ensure_columns(conn)
            cursor = conn.execute(f"INSERT INTO experiments ({', '.join(INSERTED)}) "
                                  f"VALUES ({','.join('?' for _ in INSERTED)})", [values[name] for name in INSERTED])
            conn.commit()
            return cursor.lastrowid

    def delete(self, experiment_id: int) -> bool:
        with self._write() as conn:
            cursor = conn.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
            conn.commit()
            return cursor.rowcount > 0

    def frame(self, family: str | None = None, stage: str | None = None) -> pd.DataFrame:
        """Every matching row, newest first; late columns read as absent where the table predates them."""
        query, conditions, params = "SELECT * FROM experiments", [], []
        if family is not None:
            conditions.append("family = ?")
            params.append(family)
        if stage is not None:
            conditions.append("stage = ?")
            params.append(stage)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id DESC"

        def action(conn):
            frame = pd.read_sql_query(query, conn, params=params)
            for column in LATE_COLUMNS:
                if column not in frame:
                    frame[column] = None
            return frame
        return self._read(action, pd.DataFrame(columns=list(COLUMNS)))

    def row(self, experiment_id: int) -> dict | None:
        def action(conn):
            cursor = conn.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            data = dict(zip([d[0] for d in cursor.description], row, strict=True))
            return data | {column: None for column in LATE_COLUMNS if column not in data}
        return self._read(action, None)

    def families(self) -> list:
        return self._read(lambda conn: [row[0] for row in conn.execute(
            "SELECT DISTINCT family FROM experiments WHERE family IS NOT NULL ORDER BY family")], [])
