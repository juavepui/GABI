"""Form 4 persistence with an explicit data directory and UTC clock."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gabi.infrastructure.storage.company_research import SqliteCompanyResearch

SCHEMA = """
CREATE TABLE IF NOT EXISTS insider_transactions (
    symbol TEXT NOT NULL,
    cik TEXT NOT NULL,
    accn TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    owner_name TEXT,
    owner_title TEXT,
    is_officer INTEGER,
    is_director INTEGER,
    is_ten_pct_owner INTEGER,
    is_10b5_1_plan INTEGER,
    transaction_date TEXT NOT NULL,
    transaction_code TEXT NOT NULL,
    acquired_disposed TEXT,
    shares REAL,
    price_per_share REAL,
    shares_owned_after REAL,
    filed_date TEXT,
    PRIMARY KEY (symbol, accn, line_no)
);
CREATE INDEX IF NOT EXISTS idx_insider_symbol_date ON insider_transactions (symbol, transaction_date);
CREATE TABLE IF NOT EXISTS insider_fetch_meta (
    symbol TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL
);
"""


class SqliteInsiders:
    def __init__(self, data_dir: Path, *, now: Callable[[], datetime] | None = None):
        self.path = data_dir / "gabi.db"
        self.reader = SqliteCompanyResearch(data_dir)
        self.now = now or (lambda: datetime.now(UTC))

    def save(self, symbol: str, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            if rows:
                conn.executemany(
                    "INSERT OR REPLACE INTO insider_transactions "
                    "(symbol, cik, accn, line_no, owner_name, owner_title, is_officer, is_director, "
                    "is_ten_pct_owner, is_10b5_1_plan, transaction_date, transaction_code, acquired_disposed, "
                    "shares, price_per_share, shares_owned_after, filed_date) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        (
                            r["symbol"], r["cik"], r["accn"], r["line_no"], r["owner_name"], r["owner_title"],
                            int(r["is_officer"]), int(r["is_director"]), int(r["is_ten_pct_owner"]),
                            int(r["is_10b5_1_plan"]), r["transaction_date"], r["transaction_code"],
                            r["acquired_disposed"], r["shares"], r["price_per_share"], r["shares_owned_after"],
                            r["filed_date"],
                        )
                        for r in rows
                    ],
                )
            conn.execute(
                "INSERT OR REPLACE INTO insider_fetch_meta (symbol, fetched_at) VALUES (?, ?)",
                (symbol, self.now().isoformat()),
            )
            conn.commit()



    def transactions(self, symbol: str):
        return self.reader.insider_transactions(symbol)

    def fetched_at(self, symbols: list[str]) -> dict[str, datetime | None]:
        if not symbols or not self.path.is_file():
            return {}
        result: dict[str, datetime | None] = {}
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=30)) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name='insider_fetch_meta'").fetchone() is None:
                return {}
            # Stay below SQLite parameter limits, preserving the historical map.
            for offset in range(0, len(symbols), 500):
                batch = symbols[offset:offset + 500]
                marks = ",".join("?" for _ in batch)
                rows = db.execute(f"SELECT symbol,fetched_at FROM insider_fetch_meta WHERE symbol IN ({marks})", batch)
                for symbol, value in rows:
                    try:
                        result[symbol] = datetime.fromisoformat(value)
                    except Exception:
                        result[symbol] = None
        return result

    def errors(self, failed: dict[str, str]) -> None:
        if not failed:
            return
        at = self.now().isoformat()
        cutoff = (self.now() - timedelta(days=90)).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS update_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
                    symbol TEXT, reason TEXT NOT NULL, occurred_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_update_errors_source_time ON update_errors(source, occurred_at);
            """)
            db.executemany("INSERT INTO update_errors(source,symbol,reason,occurred_at) VALUES (?,?,?,?)",
                           [("insider_form4", symbol, str(reason), at) for symbol, reason in failed.items()])
            db.execute("DELETE FROM update_errors WHERE occurred_at < ?", (cutoff,))
            db.commit()
