"""Operational cache writes (Yahoo prices, splits, fundamentals, update errors) on an explicit path and clock."""

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from gabi.infrastructure.storage.identity_writes import put_observations

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    adj_close REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS fundamentals (
    symbol TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    info_json TEXT NOT NULL,
    quarterly_income_json TEXT NOT NULL,
    quarterly_cashflow_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS splits (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    ratio REAL NOT NULL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS update_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    symbol TEXT,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_update_errors_source_time ON update_errors (source, occurred_at);
"""
ATTRIBUTION = "yahoo:explicit-entity"
PRICE_COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume", "adj_close")


def ensure_price_columns(conn: sqlite3.Connection) -> None:
    if "adj_close" not in {row[1] for row in conn.execute("PRAGMA table_info(prices)")}:
        conn.execute("ALTER TABLE prices ADD COLUMN adj_close REAL")


def statement_json(frame) -> str:
    """Financial statement (rows=line item, columns=date) as {date: {item: value}}."""
    if frame is None or frame.empty:
        return "{}"
    transposed = frame.T
    transposed.index = transposed.index.astype(str)
    transposed = transposed.apply(pd.to_numeric, errors="coerce")
    return json.dumps(transposed.to_dict(orient="index"))


def price_records(symbol: str, frame: pd.DataFrame) -> list[tuple]:
    """yfinance-shaped frame (date index, Open/High/Low/Close/Volume[/Adj Close]) as table rows."""
    frame = frame.copy().reset_index()
    frame.rename(columns={frame.columns[0]: "date"}, inplace=True)
    frame.rename(columns={"Adj Close": "Adj_Close"}, inplace=True)
    records = []
    for row in frame.itertuples(index=False):
        day = row.date
        records.append((
            symbol, day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10],
            float(row.Open) if pd.notna(row.Open) else None,
            float(row.High) if pd.notna(row.High) else None,
            float(row.Low) if pd.notna(row.Low) else None,
            float(row.Close) if pd.notna(row.Close) else None,
            float(row.Volume) if pd.notna(row.Volume) else None,
            float(row.Adj_Close) if hasattr(row, "Adj_Close") and pd.notna(row.Adj_Close) else None,
        ))
    return records


class SqliteCacheWrites:
    def __init__(self, path: Path, now: Callable[[], datetime], *, error_retention_days: int = 90):
        self.path, self.now, self.error_retention_days = path, now, error_retention_days

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # Same 30 s lock wait and WAL journal as the shared compatibility connection.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            conn.executescript(SCHEMA)
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self._connection() as conn:
            ensure_price_columns(conn)
            conn.commit()

    def prices(self, symbol: str, frame: pd.DataFrame, *, entity_id: str | None = None) -> None:
        if frame is None or frame.empty:
            return
        records = price_records(symbol, frame)
        with self._connection() as conn:
            ensure_price_columns(conn)
            conn.executemany("INSERT OR REPLACE INTO prices (symbol, date, open, high, low, close, volume, adj_close) "
                             "VALUES (?,?,?,?,?,?,?,?)", records)
            if entity_id:
                put_observations(conn, entity_id, "prices", symbol,
                                 [dict(zip(PRICE_COLUMNS, record, strict=True)) for record in records], ATTRIBUTION)
            conn.commit()

    def splits(self, symbol: str, splits: dict, *, entity_id: str | None = None) -> None:
        if not splits:
            return
        with self._connection() as conn:
            conn.executemany("INSERT OR REPLACE INTO splits (symbol, date, ratio) VALUES (?,?,?)",
                             [(symbol, day, ratio) for day, ratio in splits.items()])
            if entity_id:
                put_observations(conn, entity_id, "splits", symbol,
                                 [{"date": day, "ratio": ratio} for day, ratio in splits.items()], ATTRIBUTION)
            conn.commit()

    def fundamentals(self, symbol: str, info: dict, quarterly_income, quarterly_cashflow, *,
                     entity_id: str | None = None) -> None:
        fetched_at = self.now().isoformat()
        payload = (symbol, fetched_at, json.dumps(info), statement_json(quarterly_income),
                   statement_json(quarterly_cashflow))
        with self._connection() as conn:
            conn.execute("INSERT OR REPLACE INTO fundamentals (symbol, fetched_at, info_json, quarterly_income_json, "
                         "quarterly_cashflow_json) VALUES (?,?,?,?,?)", payload)
            if entity_id:
                put_observations(conn, entity_id, "fundamentals", symbol, [{
                    "fetched_at": fetched_at, "info": info,
                    "quarterly_income": json.loads(payload[3]), "quarterly_cashflow": json.loads(payload[4]),
                }], ATTRIBUTION)
            conn.commit()

    def update_errors(self, source: str, failed: dict) -> None:
        """Record failures and prune entries older than the retention window in the same commit."""
        if not failed:
            return
        now = self.now()
        occurred_at = now.isoformat()
        cutoff = (now - timedelta(days=self.error_retention_days)).isoformat()
        with self._connection() as conn:
            conn.executemany("INSERT INTO update_errors (source, symbol, reason, occurred_at) VALUES (?,?,?,?)",
                             [(source, symbol, str(reason), occurred_at) for symbol, reason in failed.items()])
            conn.execute("DELETE FROM update_errors WHERE occurred_at < ?", (cutoff,))
            conn.commit()
