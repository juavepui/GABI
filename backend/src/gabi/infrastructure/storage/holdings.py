"""Real holdings (#181) and their sales and dividends (#294) in gabi.db.

GET never initializes the table; every write is explicit. A table created before #294 gains the
``kind`` and ``withholding`` columns on its first write; its rows are purchases.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from gabi.application.errors import QueryError

SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio_holdings (
 id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, shares REAL NOT NULL, price REAL NOT NULL,
 purchase_date TEXT NOT NULL, currency TEXT NOT NULL, commission REAL NOT NULL DEFAULT 0, fx_rate REAL,
 note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 kind TEXT NOT NULL DEFAULT 'buy', withholding REAL NOT NULL DEFAULT 0
);
"""
COLUMNS = ("symbol", "shares", "price", "purchase_date", "currency", "commission", "fx_rate", "note", "kind",
           "withholding")
DEFAULTS = {"kind": "buy", "withholding": 0.0}  # A lot written without them is a purchase.
ADDED = {"kind": "TEXT NOT NULL DEFAULT 'buy'", "withholding": "REAL NOT NULL DEFAULT 0"}
MAX_LOTS = 200



def _value(lot: dict, column: str):
    value = lot.get(column)
    return DEFAULTS[column] if value is None and column in DEFAULTS else value


class SqliteHoldings:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def _read(self) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name='portfolio_holdings'").fetchone() is None:
            db.close()
            return None
        return db

    def _exists(self) -> bool:
        db = self._read()
        if db is None:
            return False
        db.close()
        return True

    def _write(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.executescript(SCHEMA)
        present = {row[1] for row in db.execute("PRAGMA table_info(portfolio_holdings)")}
        for column, definition in ADDED.items():
            if column not in present:
                db.execute(f"ALTER TABLE portfolio_holdings ADD COLUMN {column} {definition}")
        db.commit()
        return db

    def lots(self) -> list[dict]:
        db = self._read()
        if db is None:
            return []
        with closing(db):
            rows = db.execute("SELECT * FROM portfolio_holdings ORDER BY purchase_date,id LIMIT ?",
                              (MAX_LOTS + 1,)).fetchall()
        if len(rows) > MAX_LOTS:
            raise QueryError("resource_limit", f"La cartera supera {MAX_LOTS} compras.")
        return [{"kind": "buy", "withholding": 0.0} | dict(row) for row in rows]

    def lot(self, lot_id: int) -> dict | None:
        db = self._read()
        if db is None:
            return None
        with closing(db):
            row = db.execute("SELECT * FROM portfolio_holdings WHERE id=?", (lot_id,)).fetchone()
        return {"kind": "buy", "withholding": 0.0} | dict(row) if row is not None else None

    def add(self, lots: list[dict], now: str) -> list[int]:
        """Insert every lot or none, within the lot budget."""
        with closing(self._write()) as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM portfolio_holdings").fetchone()[0]
            if count + len(lots) > MAX_LOTS:
                db.rollback()
                raise QueryError("resource_limit", f"La cartera admite como máximo {MAX_LOTS} compras.", 422)
            marks = ",".join("?" for _ in (*COLUMNS, "created_at", "updated_at"))
            ids = []
            for lot in lots:
                cursor = db.execute(f"INSERT INTO portfolio_holdings({','.join(COLUMNS)},created_at,updated_at) "
                                    f"VALUES({marks})", (*(_value(lot, column) for column in COLUMNS), now, now))
                assert cursor.lastrowid is not None
                ids.append(int(cursor.lastrowid))
            db.commit()
            return ids

    def update(self, lot_id: int, lot: dict, now: str) -> bool:
        if not self._exists():
            return False
        with closing(self._write()) as db:
            cursor = db.execute(f"UPDATE portfolio_holdings SET {','.join(column + '=?' for column in COLUMNS)},"
                                "updated_at=? WHERE id=?", (*(_value(lot, column) for column in COLUMNS), now, lot_id))
            db.commit()
            return cursor.rowcount == 1

    def delete(self, lot_id: int) -> bool:
        if not self._exists():
            return False
        with closing(self._write()) as db:
            cursor = db.execute("DELETE FROM portfolio_holdings WHERE id=?", (lot_id,))
            db.commit()
            return cursor.rowcount == 1
