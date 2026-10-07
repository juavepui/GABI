"""Existing checkpoint/event schema on an explicitly owned SQLite connection."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_checkpoints (
    source TEXT NOT NULL, entity TEXT NOT NULL, dataset TEXT NOT NULL,
    state_json TEXT NOT NULL, PRIMARY KEY (source, entity, dataset)
);
CREATE TABLE IF NOT EXISTS sync_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, entity TEXT NOT NULL,
    dataset TEXT NOT NULL, at TEXT NOT NULL, event_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sync_events_at ON sync_events(at);
"""


class SqliteSyncEvents:
    def __init__(self, connection: sqlite3.Connection, *, max_state_bytes: int = 2_000_000):
        self.connection = connection
        self.max_state_bytes = max_state_bytes

    def get(self, source: str, entity: str, dataset: str) -> dict:
        try:
            row = self.connection.execute("SELECT CASE WHEN length(CAST(state_json AS BLOB))<=? THEN state_json END, "
                "length(CAST(state_json AS BLOB)) FROM sync_checkpoints WHERE source=? AND entity=? AND dataset=?",
                (self.max_state_bytes, source, entity, dataset)).fetchone()
        except sqlite3.OperationalError as exc:
            if str(exc) != "no such table: sync_checkpoints":
                raise
            return {}
        if not row:
            return {}
        if row[1] > self.max_state_bytes:
            raise ValueError("Sync checkpoint byte limit exceeded")
        return json.loads(row[0])

    def save(self, event: dict, checkpoint: dict, *, skipped: bool) -> None:
        checkpoint_json, event_json = json.dumps(checkpoint), json.dumps(event)
        if max(len(checkpoint_json.encode("utf8")), len(event_json.encode("utf8"))) > self.max_state_bytes:
            raise ValueError("Sync checkpoint/event byte limit exceeded")
        self.connection.executescript(SCHEMA)
        with self.connection:
            if not skipped:
                self.connection.execute("INSERT INTO sync_checkpoints VALUES (?,?,?,?) "
                    "ON CONFLICT(source,entity,dataset) DO UPDATE SET state_json=excluded.state_json",
                    (event["source"], event["entity"], event["dataset"], checkpoint_json))
            self.connection.execute("INSERT INTO sync_events(source,entity,dataset,at,event_json) VALUES (?,?,?,?,?)",
                (event["source"], event["entity"], event["dataset"], event["at"], event_json))


class OperationSyncEvents:
    """Do not hold a connection during network retries; reads never create a DB."""

    def __init__(self, path: Path):
        self.path = path

    def get(self, source: str, entity: str, dataset: str) -> dict:
        if not self.path.is_file():
            return {}
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as connection:
            connection.execute("PRAGMA query_only=ON")
            return SqliteSyncEvents(connection).get(source, entity, dataset)

    def save(self, event: dict, checkpoint: dict, *, skipped: bool) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as connection:
            SqliteSyncEvents(connection).save(event, checkpoint, skipped=skipped)
