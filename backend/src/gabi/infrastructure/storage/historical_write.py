"""Transaction primitives for explicit historical archive and audit imports."""

import sqlite3
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path

from gabi.domain.market.identity import require_same_cik
from gabi.infrastructure.storage.identity_writes import ensure_schema


@contextmanager
def transaction(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('BEGIN IMMEDIATE')
        with db:
            yield db


def initialize(conn, schema: str) -> None:
    # executescript commits an existing transaction, so execute DDL individually.
    for statement in schema.split(';'):
        if statement.strip():
            conn.execute(statement)


def ensure_entity(conn, cik: str, today: date) -> str:
    ensure_schema(conn)
    entity = f'cik:{cik}'
    existing = conn.execute('SELECT cik FROM entities WHERE entity_id=?', (entity,)).fetchone()
    require_same_cik(existing, cik)
    conn.execute('INSERT INTO entities VALUES (?,?,?,?) ON CONFLICT(entity_id) DO NOTHING',
                 (entity, cik, None, today.isoformat()))
    return entity
