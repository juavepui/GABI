"""SQLite store of the versioned investment cards (#246) in ``gabi.db``.

A version is one row. Published and discarded rows are never edited again, apart
from discarding a published one, which keeps its content and snapshot.
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS investment_cards (
 id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, version INTEGER NOT NULL,
 state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 published_at TEXT, discarded_at TEXT, discard_reason TEXT,
 content_json TEXT NOT NULL, snapshot_json TEXT, snapshot_sha256 TEXT,
 UNIQUE(symbol, version)
);
CREATE INDEX IF NOT EXISTS idx_investment_cards_symbol ON investment_cards(symbol, version);
"""
COLUMNS = ("id", "symbol", "version", "state", "created_at", "updated_at", "published_at", "discarded_at",
           "discard_reason", "content_json", "snapshot_json", "snapshot_sha256")
EDITABLE = ("incompleta", "analizada")


def _row(values: tuple) -> dict:
    row = dict(zip(COLUMNS, values, strict=True))
    row["content"] = json.loads(row.pop("content_json"))
    snapshot = row.pop("snapshot_json")
    row["snapshot"] = json.loads(snapshot) if snapshot else None
    return row


class SqliteInvestmentCards:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def _read(self) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name='investment_cards'").fetchone() is None:
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

    def list(self, symbol: str | None, limit: int) -> list[dict]:
        db = self._read()
        if db is None:
            return []
        where, values = ("WHERE symbol=?", (symbol,)) if symbol else ("", ())
        with closing(db):
            rows = db.execute(f"SELECT {','.join(COLUMNS)} FROM investment_cards {where} "
                              "ORDER BY symbol, version DESC LIMIT ?", (*values, limit)).fetchall()
        return [_row(row) for row in rows]

    def get(self, card_id: int) -> dict | None:
        db = self._read()
        if db is None:
            return None
        with closing(db):
            row = db.execute(f"SELECT {','.join(COLUMNS)} FROM investment_cards WHERE id=?", (card_id,)).fetchone()
        return _row(row) if row else None

    def create(self, symbol: str, version: int, content: dict, now: str) -> int:
        with closing(self._write()) as db, db:
            cursor = db.execute("INSERT INTO investment_cards(symbol,version,state,created_at,updated_at,content_json) "
                                "VALUES (?,?,?,?,?,?)", (symbol, version, "incompleta", now, now,
                                                         json.dumps(content, ensure_ascii=False)))
            return int(cursor.lastrowid or 0)

    def update(self, card_id: int, content: dict, state: str, now: str) -> bool:
        with closing(self._write()) as db, db:
            cursor = db.execute("UPDATE investment_cards SET content_json=?, state=?, updated_at=? "
                                f"WHERE id=? AND state IN ({','.join('?' * len(EDITABLE))})",
                                (json.dumps(content, ensure_ascii=False), state, now, card_id, *EDITABLE))
            return cursor.rowcount == 1

    def publish(self, card_id: int, content: dict, snapshot: dict, digest: str, now: str) -> bool:
        with closing(self._write()) as db, db:
            cursor = db.execute(
                "UPDATE investment_cards SET state='publicada', content_json=?, snapshot_json=?, snapshot_sha256=?, "
                f"published_at=?, updated_at=? WHERE id=? AND state IN ({','.join('?' * len(EDITABLE))})",
                (json.dumps(content, ensure_ascii=False), json.dumps(snapshot, ensure_ascii=False, default=str),
                 digest, now, now, card_id, *EDITABLE))
            return cursor.rowcount == 1

    def discard(self, card_id: int, reason: str, now: str) -> bool:
        with closing(self._write()) as db, db:
            cursor = db.execute("UPDATE investment_cards SET state='descartada', discard_reason=?, discarded_at=?, "
                                "updated_at=? WHERE id=? AND state!='descartada'", (reason, now, now, card_id))
            return cursor.rowcount == 1
