"""Existing simulated portfolios and trades, with read-only GET and bounded prices."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from gabi.application.errors import QueryError

SCHEMA = """
CREATE TABLE IF NOT EXISTS sim_portfolios (
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
 initial_cash REAL NOT NULL, stock_commission REAL NOT NULL,
 etf_commission REAL NOT NULL, spread_bps REAL NOT NULL,
 created_at TEXT NOT NULL, base_currency TEXT NOT NULL DEFAULT 'USD'
);
CREATE TABLE IF NOT EXISTS sim_trades (
 id INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id INTEGER NOT NULL,
 symbol TEXT NOT NULL, asset_type TEXT NOT NULL, side TEXT NOT NULL,
 requested_date TEXT NOT NULL, execution_date TEXT NOT NULL,
 reference_close REAL NOT NULL, notional REAL NOT NULL,
 commission REAL NOT NULL, spread_bps REAL NOT NULL, created_at TEXT NOT NULL,
 market TEXT NOT NULL DEFAULT 'XNYS', quote_currency TEXT NOT NULL DEFAULT 'USD',
 fx_rate REAL NOT NULL DEFAULT 1, fx_fee_bps REAL NOT NULL DEFAULT 0,
 FOREIGN KEY (portfolio_id) REFERENCES sim_portfolios(id)
);
CREATE INDEX IF NOT EXISTS idx_sim_trades_portfolio_date ON sim_trades(portfolio_id,execution_date,id);
"""
TRADE_COLUMNS = ("portfolio_id", "symbol", "asset_type", "side", "requested_date", "execution_date",
                 "reference_close", "notional", "commission", "spread_bps", "created_at", "market",
                 "quote_currency", "fx_rate", "fx_fee_bps")


class SqliteSimulations:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def _read(self, table: str) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (table,)).fetchone() is None:
            db.close()
            return None
        return db

    def portfolios(self) -> list[dict]:
        db = self._read("sim_portfolios")
        if db is None:
            return []
        with closing(db):
            rows = db.execute("SELECT * FROM sim_portfolios ORDER BY id DESC LIMIT 100").fetchall()
            return [dict(row) | {"base_currency": dict(row).get("base_currency", "USD")} for row in rows]

    def portfolio(self, portfolio_id: int) -> dict | None:
        db = self._read("sim_portfolios")
        if db is None:
            return None
        with closing(db):
            row = db.execute("SELECT * FROM sim_portfolios WHERE id=?", (portfolio_id,)).fetchone()
            return dict(row) | {"base_currency": dict(row).get("base_currency", "USD")} if row else None

    def trades(self, portfolio_id: int) -> list[dict]:
        db = self._read("sim_trades")
        if db is None:
            return []
        with closing(db):
            rows = db.execute("SELECT * FROM sim_trades WHERE portfolio_id=? ORDER BY execution_date,id LIMIT 501",
                              (portfolio_id,)).fetchall()
            if len(rows) > 500:
                raise QueryError("resource_limit", "La cartera supera 500 operaciones.")
            defaults = {"market": "XNYS", "quote_currency": "USD", "fx_rate": 1.0, "fx_fee_bps": 0.0}
            return [defaults | dict(row) for row in rows]

    def prices(self, symbols: list[str], start: str) -> dict[str, pd.DataFrame]:
        if not symbols:
            return {}
        if len(symbols) > 30:
            raise QueryError("resource_limit", "La cartera supera el límite de 30 símbolos.")
        db = self._read("prices")
        if db is None:
            return {}
        with closing(db):
            result = {}
            for symbol in symbols:
                rows = db.execute("SELECT date,open,high,low,close,volume,adj_close FROM prices "
                                  "WHERE symbol=? AND date>=? ORDER BY date LIMIT 10001", (symbol, start)).fetchall()
                if len(rows) > 10000:
                    raise QueryError("resource_limit", "El historial supera 10000 sesiones por símbolo.")
                if rows:
                    frame = pd.DataFrame([dict(row) for row in rows])
                    frame["date"] = pd.to_datetime(frame["date"])
                    result[symbol] = frame.set_index("date")
            return result

    def create(self, portfolio: dict) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.executescript(SCHEMA)
            for table, updates in (("sim_portfolios", {"base_currency": "TEXT NOT NULL DEFAULT 'USD'"}),
                                   ("sim_trades", {"market": "TEXT NOT NULL DEFAULT 'XNYS'",
                                                   "quote_currency": "TEXT NOT NULL DEFAULT 'USD'",
                                                   "fx_rate": "REAL NOT NULL DEFAULT 1",
                                                   "fx_fee_bps": "REAL NOT NULL DEFAULT 0"})):
                existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                for column, definition in updates.items():
                    if column not in existing:
                        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            try:
                cursor = db.execute("INSERT INTO sim_portfolios(name,initial_cash,stock_commission,etf_commission,"
                                    "spread_bps,created_at,base_currency) VALUES(?,?,?,?,?,?,?)",
                                    tuple(portfolio[key] for key in ("name", "initial_cash", "stock_commission",
                                                                    "etf_commission", "spread_bps", "created_at",
                                                                    "base_currency")))
            except sqlite3.IntegrityError as exc:
                raise QueryError("name_exists", "Ya existe una cartera con ese nombre.", 409) from exc
            db.commit()
            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

    def add_trade(self, trade: dict, previous_id: int) -> int:
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("BEGIN IMMEDIATE")
            latest = db.execute("SELECT COALESCE(MAX(id),0) FROM sim_trades WHERE portfolio_id=?",
                                (trade["portfolio_id"],)).fetchone()[0]
            if latest != previous_id:
                raise QueryError("portfolio_changed", "La cartera cambió durante la operación; vuelve a intentarlo.", 409)
            marks = ",".join("?" for _ in TRADE_COLUMNS)
            cursor = db.execute(f"INSERT INTO sim_trades({','.join(TRADE_COLUMNS)}) VALUES({marks})",
                                tuple(trade[key] for key in TRADE_COLUMNS))
            db.commit()
            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

    def undo_last(self, portfolio_id: int, expected_id: int) -> bool:
        if not self.path.is_file():
            return False
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("BEGIN IMMEDIATE")
            latest = db.execute("SELECT COALESCE(MAX(id),0) FROM sim_trades WHERE portfolio_id=?",
                                (portfolio_id,)).fetchone()[0]
            if latest != expected_id:
                raise QueryError("portfolio_changed", "La cartera cambió durante la operación; vuelve a intentarlo.", 409)
            cursor = db.execute("DELETE FROM sim_trades WHERE id=? AND portfolio_id=?", (expected_id, portfolio_id))
            db.commit()
            return cursor.rowcount == 1
