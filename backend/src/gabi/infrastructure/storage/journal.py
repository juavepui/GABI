"""Journal adapter for the existing gabi.db table; GET never initializes it."""

import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_entries (
 id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, created_at TEXT NOT NULL,
 horizon TEXT, entry_price REAL, thesis TEXT, bear_price REAL, base_price REAL, bull_price REAL,
 bear_prob REAL, base_prob REAL, bull_prob REAL, catalysts TEXT, risks TEXT,
 position_size_pct REAL, notes TEXT, status TEXT NOT NULL DEFAULT 'abierta',
 review_date TEXT, review_price REAL, review_notes TEXT
);
"""
CREATE_COLUMNS = ("symbol", "created_at", "horizon", "entry_price", "thesis", "bear_price", "base_price",
                  "bull_price", "bear_prob", "base_prob", "bull_prob", "catalysts", "risks",
                  "position_size_pct", "notes")


class SqliteJournal:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def _read(self) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name='journal_entries'").fetchone() is None:
            db.close()
            return None
        return db

    def list_entries(self, limit: int, offset: int, only_open: bool = False) -> tuple[list[dict], int]:
        db = self._read()
        if db is None:
            return [], 0
        where = " WHERE status='abierta'" if only_open else ""
        with closing(db):
            total = int(db.execute("SELECT COUNT(*) FROM journal_entries" + where).fetchone()[0])
            rows = db.execute("SELECT * FROM journal_entries" + where +
                              " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            return [dict(row) for row in rows], total

    def get(self, entry_id: int) -> dict | None:
        db = self._read()
        if db is None:
            return None
        with closing(db):
            row = db.execute("SELECT * FROM journal_entries WHERE id=?", (entry_id,)).fetchone()
            return dict(row) if row is not None else None

    def create(self, entry: dict) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.executescript(SCHEMA)
            placeholders = ",".join("?" for _ in CREATE_COLUMNS)
            cursor = db.execute(
                f"INSERT INTO journal_entries ({','.join(CREATE_COLUMNS)}) VALUES ({placeholders})",
                tuple(entry.get(column) for column in CREATE_COLUMNS),
            )
            db.commit()
            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

    def review(self, entry_id: int, review_date: str, review_price: float | None, notes: str) -> bool:
        if not self.path.is_file():
            return False
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name='journal_entries'").fetchone() is None:
                return False
            cursor = db.execute(
                "UPDATE journal_entries SET review_date=?,review_price=?,review_notes=?,status='revisada' "
                "WHERE id=? AND status='abierta'", (review_date, review_price, notes, entry_id),
            )
            db.commit()
            return cursor.rowcount == 1

    def delete(self, entry_id: int) -> bool:
        if not self.path.is_file():
            return False
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name='journal_entries'").fetchone() is None:
                return False
            cursor = db.execute("DELETE FROM journal_entries WHERE id=?", (entry_id,))
            db.commit()
            return cursor.rowcount == 1
