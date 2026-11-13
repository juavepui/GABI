"""Explicit issuer writes and caller-owned atomic observation dual-writes."""

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path

from gabi.domain.market.identity import (
    DATA_KEYS,
    _json_value,
    alias_evidence,
    entity_definition,
    normalize_symbol,
    require_same_cik,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY, cik TEXT UNIQUE, name TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_aliases (
    entity_id TEXT NOT NULL REFERENCES entities(entity_id), symbol TEXT NOT NULL,
    valid_from TEXT NOT NULL, valid_to TEXT, source TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    PRIMARY KEY(entity_id, symbol, valid_from, source),
    CHECK(valid_to IS NULL OR valid_to > valid_from)
);
CREATE INDEX IF NOT EXISTS idx_entity_alias_symbol ON entity_aliases(symbol, valid_from, valid_to);
CREATE TABLE IF NOT EXISTS entity_observations (
    entity_id TEXT NOT NULL REFERENCES entities(entity_id), dataset TEXT NOT NULL,
    symbol TEXT NOT NULL, record_key TEXT NOT NULL, payload_json TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY(entity_id, dataset, symbol, record_key)
);
CREATE INDEX IF NOT EXISTS idx_entity_observations_dataset_symbol
    ON entity_observations(dataset, symbol);
CREATE TABLE IF NOT EXISTS entity_candidates (
    symbol TEXT NOT NULL, entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    name TEXT, source TEXT NOT NULL, reason TEXT NOT NULL,
    PRIMARY KEY(symbol, entity_id, source)
);
"""


def ensure_schema(conn):
    # execute, rather than executescript: do not commit the caller's transaction.
    for statement in SCHEMA.split(";"):
        if statement.strip():
            conn.execute(statement)


def put_observations(conn, entity_id: str, dataset: str, symbol: str, rows: list[dict], source: str):
    """Atomic dual-write used by ingestion; attribution must be explicit."""
    ensure_schema(conn)
    if dataset not in DATA_KEYS or not source:
        raise ValueError("Unknown dataset or missing attribution source")
    if not conn.execute("SELECT 1 FROM entities WHERE entity_id=?", (entity_id,)).fetchone():
        raise ValueError("Unknown entity")
    records = []
    for row in rows:
        row = _json_value(row)
        key = json.dumps([row.get(k, "") for k in DATA_KEYS[dataset]], separators=(",", ":"))
        payload = json.dumps(row, sort_keys=True, default=str, allow_nan=False)
        records.append((entity_id, dataset, normalize_symbol(symbol), key, payload, source))
    if dataset == "edgar_facts":
        # A filing fact is issuer-wide. A refresh under a new alias supersedes
        # the same fact downloaded under the former ticker, not an arbitrary
        # alphabetical duplicate selected at read time.
        conn.executemany("DELETE FROM entity_observations WHERE entity_id=? AND dataset=? AND record_key=?",
                         [(entity_id, dataset, r[3]) for r in records])
    conn.executemany("INSERT OR REPLACE INTO entity_observations VALUES (?,?,?,?,?,?)", records)


def put_facts(connection, entity: str, symbol: str, rows: list[dict], source: str) -> None:
    put_observations(connection, entity, "edgar_facts", symbol, rows, source)


class SqliteIdentityWrites:
    def __init__(self, path: Path, today: Callable[[], date], new_id: Callable[[], str]):
        self.path, self.today, self.new_id = path, today, new_id

    @contextmanager
    def _write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            with db:
                yield db

    def ensure_entity(self, cik=None, name: str | None = None, *, entity_id: str | None = None) -> str:
        local_id = self.new_id() if cik is None and not entity_id else ""
        derived, cik, name = entity_definition(cik, name, entity_id, local_id)
        with self._write() as conn:
            ensure_schema(conn)
            existing = conn.execute("SELECT cik FROM entities WHERE entity_id=?", (derived,)).fetchone()
            require_same_cik(existing, cik)
            conn.execute("INSERT INTO entities VALUES (?,?,?,?) ON CONFLICT(entity_id) DO UPDATE "
                         "SET name=COALESCE(excluded.name,entities.name)",
                         (derived, cik, name, self.today().isoformat()))
            conn.commit()
        return derived

    def add_alias(self, entity_id: str, symbol: str, valid_from: str, valid_to: str | None = None,
                  *, source: str, confidence: float = 1.0):
        """Record dated evidence. Conflicting evidence is retained as ambiguous."""
        symbol, start, end, source, confidence = alias_evidence(symbol, valid_from, valid_to, source, confidence)
        with self._write() as conn:
            ensure_schema(conn)
            if not conn.execute("SELECT 1 FROM entities WHERE entity_id=?", (entity_id,)).fetchone():
                raise ValueError("Unknown entity")
            conn.execute("INSERT INTO entity_aliases VALUES (?,?,?,?,?,?) "
                         "ON CONFLICT(entity_id,symbol,valid_from,source) DO UPDATE SET "
                         "valid_to=excluded.valid_to, confidence=excluded.confidence",
                         (entity_id, symbol, start, end, source, confidence))
            conn.commit()

    def candidate(self, symbol: str, entity: str, name: str, source: str) -> None:
        with self._write() as db:
            db.execute("INSERT OR REPLACE INTO entity_candidates VALUES (?,?,?,?,?)",
                       (normalize_symbol(symbol), entity, name, source,
                        "Exact normalized name/formerNames match; requires dated ticker evidence"))
