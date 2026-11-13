"""Empresas seguidas (#182) in gabi.db: GET never initializes the table; every write is explicit."""

import sqlite3
from contextlib import closing
from pathlib import Path

from gabi.application.errors import QueryError
from gabi.domain.market.watchlist import MAX_COMPANIES

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
 symbol TEXT PRIMARY KEY, added_at TEXT NOT NULL, note TEXT, model_id TEXT, score_at_add REAL,
 rank_at_add INTEGER, updated_at TEXT NOT NULL
);
"""
COLUMNS = ("symbol", "added_at", "note", "model_id", "score_at_add", "rank_at_add")


class SqliteWatchlist:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def _read(self) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name='watchlist'").fetchone() is None:
            db.close()
            return None
        return db

    def _write(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.executescript(SCHEMA)
        return db

    def items(self) -> list[dict]:
        db = self._read()
        if db is None:
            return []
        with closing(db):
            rows = db.execute("SELECT * FROM watchlist ORDER BY added_at,symbol LIMIT ?",
                              (MAX_COMPANIES + 1,)).fetchall()
        if len(rows) > MAX_COMPANIES:
            raise QueryError("resource_limit", f"La lista supera {MAX_COMPANIES} empresas.")
        return [dict(row) for row in rows]

    def item(self, symbol: str) -> dict | None:
        db = self._read()
        if db is None:
            return None
        with closing(db):
            row = db.execute("SELECT * FROM watchlist WHERE symbol=?", (symbol,)).fetchone()
        return dict(row) if row is not None else None

    def add(self, item: dict, now: str) -> bool:
        """False when the company was already followed: its date, note and starting score are kept."""
        with closing(self._write()) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM watchlist WHERE symbol=?", (item["symbol"],)).fetchone():
                db.rollback()
                return False
            if db.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] >= MAX_COMPANIES:
                db.rollback()
                raise QueryError("resource_limit", f"Puedes seguir como máximo {MAX_COMPANIES} empresas.", 422)
            db.execute(f"INSERT INTO watchlist({','.join(COLUMNS)},updated_at) VALUES({','.join('?' * 7)})",
                       (*(item.get(column) for column in COLUMNS), now))
            db.commit()
            return True

    def update_note(self, symbol: str, note: str | None, now: str) -> bool:
        if self.item(symbol) is None:
            return False
        with closing(self._write()) as db:
            cursor = db.execute("UPDATE watchlist SET note=?,updated_at=? WHERE symbol=?", (note, now, symbol))
            db.commit()
            return cursor.rowcount == 1

    def delete(self, symbol: str) -> bool:
        if self.item(symbol) is None:
            return False
        with closing(self._write()) as db:
            cursor = db.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))
            db.commit()
            return cursor.rowcount == 1
