"""Dated sector snapshots: bounded read-only lookups and one-transaction writes with attributed observations."""

import sqlite3
from contextlib import closing
from pathlib import Path

from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only
from gabi.infrastructure.storage.identity_writes import put_observations

SCHEMA = """
CREATE TABLE IF NOT EXISTS entity_snapshots (
    symbol TEXT NOT NULL,
    cik TEXT,
    name TEXT,
    sector TEXT,
    industry TEXT,
    effective_date TEXT NOT NULL,
    PRIMARY KEY (symbol, effective_date)
);
CREATE INDEX IF NOT EXISTS idx_entity_snapshots_symbol ON entity_snapshots (symbol, effective_date);
"""
SOURCE = "observed-universe-snapshot"


class SqliteEntitySnapshots:
    def __init__(self, path: Path, *, max_rows: int = 500_000, max_bytes: int = 256 * 1024 * 1024,
                 max_field_bytes: int = 64 * 1024, batch_size: int = 500):
        if min(max_rows, max_bytes, max_field_bytes, batch_size) < 1 or batch_size > 500:
            raise ValueError("Invalid entity snapshot limits")
        self.path, self.max_rows, self.max_bytes = path, max_rows, max_bytes
        self.max_field_bytes, self.batch_size = max_field_bytes, batch_size

    def rows(self, symbols: list[str]) -> list[tuple]:
        symbols = list(dict.fromkeys(symbols))
        found: list[tuple] = []
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "entity_snapshots" not in tables:
                return found
            for start in range(0, len(symbols), self.batch_size):
                chunk = symbols[start:start + self.batch_size]
                found += bounded_rows(db, "SELECT symbol,cik,name,sector,industry,effective_date FROM entity_snapshots "
                                      "WHERE symbol IN (" + ",".join("?" for _ in chunk) + ")", tuple(chunk),
                                      max_rows=self.max_rows - len(found), max_bytes=self.max_bytes,
                                      max_field_bytes=self.max_field_bytes)
        return found

    def record(self, rows: list[tuple], attributed: list[tuple[str, str, dict]]) -> None:
        """Snapshots and their entity observations commit together or not at all."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.executescript(SCHEMA)
            with db:
                db.executemany("INSERT OR REPLACE INTO entity_snapshots (symbol, cik, name, sector, industry, "
                               "effective_date) VALUES (?,?,?,?,?,?)", rows)
                for entity_id, symbol, payload in attributed:
                    put_observations(db, entity_id, "sector", symbol, [payload], SOURCE)
