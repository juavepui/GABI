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

    def import_prices(self, source_id: str, frame: pd.DataFrame, symbols: set[str], start: str, end: str) -> dict:
        frame, rejected = prepare_price_chunk(frame, symbols, start, end)
        records = [(source_id, row.symbol, row.date, row.open, row.high, row.low, row.close, row.adj_close,
                    row.volume, "as_traded") for row in frame.itertuples(index=False)]
        self.connection.executescript(SCHEMA)
        with self.connection:
            self.connection.executemany("INSERT OR IGNORE INTO historical_prices VALUES (?,?,?,?,?,?,?,?,?,?)", records)
        return {"accepted": len(records), "rejected": rejected}
