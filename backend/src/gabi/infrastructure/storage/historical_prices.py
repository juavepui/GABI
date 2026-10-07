"""Operation-owned archive price persistence; never activates an identity alias."""

import json
import sqlite3

import pandas as pd

from gabi.domain.research.historical_prices import prepare_price_chunk

SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_sources (
 source_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historical_prices (
 source_id TEXT NOT NULL, symbol TEXT NOT NULL, date TEXT NOT NULL,
 open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL,
 close_basis TEXT NOT NULL,
 PRIMARY KEY(source_id,symbol,date)
);
"""


class SqliteHistoricalPrices:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def register(self, source_id: str, metadata: dict) -> None:
        self.connection.executescript(SCHEMA)
        self.connection.execute("INSERT OR REPLACE INTO historical_sources VALUES (?,?)",
                                (source_id, json.dumps(metadata, sort_keys=True)))
        self.connection.commit()

    def pinned(self, source_id: str, *, max_bytes: int = 2_000_000) -> dict:
        try:
            row = self.connection.execute("SELECT CASE WHEN length(CAST(metadata_json AS BLOB))<=? THEN metadata_json END, "
                "length(CAST(metadata_json AS BLOB)) FROM historical_sources WHERE source_id=?", (max_bytes, source_id)).fetchone()
        except sqlite3.OperationalError as exc:
            if str(exc) != "no such table: historical_sources":
                raise
            return {}
        if not row:
            return {}
        if row[1] > max_bytes:
            raise ValueError("Historical source metadata byte limit exceeded")
        return json.loads(row[0]).get("files_sha256", {})

    def dates(self, source_id: str, symbol: str, first: str, last: str, *, max_rows: int = 10_000) -> pd.DatetimeIndex:
        try:
            rows = self.connection.execute("SELECT date FROM historical_prices WHERE source_id=? AND symbol=? AND date>=? AND date<? "
                "ORDER BY date LIMIT ?", (source_id, symbol.replace(".", "-"), first, last, max_rows + 1)).fetchall()
        except sqlite3.OperationalError as exc:
            if str(exc) != "no such table: historical_prices":
                raise
            return pd.DatetimeIndex([])
        if len(rows) > max_rows:
            raise ValueError("Historical price date row limit exceeded")
        return pd.DatetimeIndex(pd.to_datetime([row[0] for row in rows]))

    def import_prices(self, source_id: str, frame: pd.DataFrame, symbols: set[str], start: str, end: str) -> dict:
        frame, rejected = prepare_price_chunk(frame, symbols, start, end)
        records = [(source_id, row.symbol, row.date, row.open, row.high, row.low, row.close, row.adj_close,
                    row.volume, "as_traded") for row in frame.itertuples(index=False)]
        self.connection.executescript(SCHEMA)
        with self.connection:
            self.connection.executemany("INSERT OR IGNORE INTO historical_prices VALUES (?,?,?,?,?,?,?,?,?,?)", records)
        return {"accepted": len(records), "rejected": rejected}
