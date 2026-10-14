"""Explicit offline identity-migration SQL: legacy snapshots, operator attribution and alias evidence."""

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path

import pandas as pd

from gabi.infrastructure.storage.identity_writes import ensure_schema, put_observations


class SqliteEntityMigration:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # Same 30 s lock wait and WAL journal as the compatibility connection it replaces.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn

    def legacy_snapshots(self) -> list[tuple]:
        """Create the identity schema and return dated legacy sector snapshots, if the table exists."""
        with self._connection() as conn:
            ensure_schema(conn)
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='entity_snapshots'").fetchone()
            rows = conn.execute("SELECT symbol,cik,name,sector,industry,effective_date FROM entity_snapshots").fetchall() if exists else []
            conn.commit()
        return rows

    def put_snapshot(self, entity_id: str, symbol: str, row: dict, source: str) -> None:
        with self._connection() as conn:
            put_observations(conn, entity_id, "sector", symbol, [row], source)
            conn.commit()

    def attribute(self, symbol: str, entity_id: str, dataset: str, source: str,
                  select: Callable[[pd.DataFrame], list[dict]]) -> int:
        """One transaction: read the legacy rows of a validated dataset and record the selected ones."""
        with self._connection() as conn:
            ensure_schema(conn)
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (dataset,)).fetchone():
                return 0
            frame = pd.read_sql_query(f'SELECT * FROM "{dataset}" WHERE symbol=?', conn, params=(symbol,))
            rows = select(frame)
            put_observations(conn, entity_id, dataset, symbol, rows, source)
            conn.commit()
        return len(rows)

    def aliases(self) -> pd.DataFrame:
        with self._connection() as conn:
            ensure_schema(conn)
            return pd.read_sql_query("SELECT * FROM entity_aliases", conn)
