"""SQLite store of the idea history (#247) in ``gabi.db``: events are only inserted, notes are editable.

``idea_events`` has no UPDATE or DELETE path: a correction is a new event. Private
notes live in ``idea_notes`` and can be edited or deleted without touching any event.
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS idea_events (
 idea_id INTEGER NOT NULL, sequence INTEGER NOT NULL, kind TEXT NOT NULL, recorded_at TEXT NOT NULL,
 payload_json TEXT NOT NULL, previous_sha256 TEXT, sha256 TEXT NOT NULL,
 PRIMARY KEY(idea_id, sequence)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_idea_events_publication ON idea_events(idea_id) WHERE kind='publicada';
CREATE TABLE IF NOT EXISTS idea_notes (
 id INTEGER PRIMARY KEY AUTOINCREMENT, idea_id INTEGER NOT NULL, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, text TEXT NOT NULL
);
"""
EVENT_COLUMNS = ("idea_id", "sequence", "kind", "recorded_at", "payload_json", "previous_sha256", "sha256")


def _event(row: tuple) -> dict:
    event = dict(zip(EVENT_COLUMNS, row, strict=True))
    event["payload"] = json.loads(event.pop("payload_json"))
    return event


class SqliteIdeas:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def _read(self) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name='idea_events'").fetchone() is None:
            db.close()
            return None
        return db

    def _write(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        for statement in SCHEMA.strip().split(";"):
            if statement.strip():
                db.execute(statement)
        return db

    def ideas(self, limit: int) -> list[int]:
        db = self._read()
        if db is None:
            return []
        with closing(db):
            return [row[0] for row in db.execute(
                "SELECT idea_id FROM idea_events WHERE kind='publicada' ORDER BY recorded_at DESC, idea_id DESC "
                "LIMIT ?", (limit,))]

    def events(self, idea_id: int) -> list[dict]:
        db = self._read()
        if db is None:
            return []
        with closing(db):
            rows = db.execute(f"SELECT {','.join(EVENT_COLUMNS)} FROM idea_events WHERE idea_id=? ORDER BY sequence",
                              (idea_id,)).fetchall()
        return [_event(row) for row in rows]

    def append(self, event: dict) -> bool:
        """Inserts the event if its sequence is still free; False when another write got there first."""
        with closing(self._write()) as db, db:
            try:
                db.execute(f"INSERT INTO idea_events({','.join(EVENT_COLUMNS)}) VALUES (?,?,?,?,?,?,?)",
                           (event["idea_id"], event["sequence"], event["kind"], event["recorded_at"],
                            json.dumps(event["payload"], ensure_ascii=False, default=str), event["previous_sha256"],
                            event["sha256"]))
            except sqlite3.IntegrityError:
                return False
        return True

    def notes(self, idea_id: int) -> list[dict]:
        db = self._read()
        if db is None:
            return []
        with closing(db):
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name='idea_notes'").fetchone() is None:
                return []
            rows = db.execute("SELECT id,idea_id,created_at,updated_at,text FROM idea_notes WHERE idea_id=? "
                              "ORDER BY id DESC", (idea_id,)).fetchall()
        return [dict(zip(("id", "idea_id", "created_at", "updated_at", "text"), row, strict=True)) for row in rows]

    def add_note(self, idea_id: int, text: str, now: str) -> int:
        with closing(self._write()) as db, db:
            return int(db.execute("INSERT INTO idea_notes(idea_id,created_at,updated_at,text) VALUES (?,?,?,?)",
                                  (idea_id, now, now, text)).lastrowid or 0)

    def save_note(self, note_id: int, text: str, now: str) -> bool:
        with closing(self._write()) as db, db:
            return db.execute("UPDATE idea_notes SET text=?, updated_at=? WHERE id=?",
                              (text, now, note_id)).rowcount == 1

    def delete_note(self, note_id: int) -> bool:
        with closing(self._write()) as db, db:
            return db.execute("DELETE FROM idea_notes WHERE id=?", (note_id,)).rowcount == 1
