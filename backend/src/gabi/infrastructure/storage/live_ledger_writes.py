"""Append-only prospective ledger SQL on an explicit path; chain checks and the anchor stay with the caller."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS live_ledger (
    seq INTEGER PRIMARY KEY, prev_hash TEXT NOT NULL, record_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS live_ledger_no_update BEFORE UPDATE ON live_ledger
BEGIN SELECT RAISE(ABORT, 'live ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS live_ledger_no_delete BEFORE DELETE ON live_ledger
BEGIN SELECT RAISE(ABORT, 'live ledger is append-only'); END;
"""


@contextmanager
def connection(path: Path) -> Iterator[sqlite3.Connection]:
    """The ledger's own connection: same 30 s lock wait and WAL journal it was always written with."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        conn.executescript(SCHEMA)
        yield conn
    finally:
        conn.close()


def chain(conn: sqlite3.Connection):
    return conn.execute("SELECT seq,prev_hash,record_hash,payload_json FROM live_ledger ORDER BY seq")


def record_hash(conn: sqlite3.Connection, seq: object) -> str | None:
    # The anchor seq comes from JSON and was always bound as-is, so a malformed anchor stays unmatched.
    row = conn.execute("SELECT record_hash FROM live_ledger WHERE seq=?", (seq,)).fetchone()
    return row[0] if row else None


def insert(conn: sqlite3.Connection, seq: int, previous: str, digest: str, payload_json: str) -> None:
    conn.execute("INSERT INTO live_ledger VALUES (?,?,?,?)", (seq, previous, digest, payload_json))


def entries(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute("SELECT seq,record_hash,payload_json FROM live_ledger ORDER BY seq").fetchall()
