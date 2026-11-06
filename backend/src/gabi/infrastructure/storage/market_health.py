"""Bounded read-only inputs of the market traffic light (#308): a price window and the VIX from FRED.

Nothing is created or written: a missing database or table reads as empty.
"""

import csv
import io
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from gabi.domain.market.identity import normalize_symbol

MAX_ROWS = 600_000  # ~520 companies × ~500 sessions plus the index; a larger read is refused.


class SqliteMarketHealth:
    def __init__(self, data_dir: Path):
        self.path, self.universe_path = data_dir / "gabi.db", data_dir / "sp500_constituents.csv"

    def stamp(self) -> tuple:
        """Changes when the database or the universe file is written: the cache key of the use case."""
        def one(path: Path):
            try:
                stat = path.stat()
            except OSError:
                return None
            return stat.st_mtime_ns, stat.st_size
        return one(self.path), one(self.path.with_name("gabi.db-wal")), one(self.universe_path)

    def universe(self) -> list[str]:
        try:
            text = self.universe_path.read_text(encoding="utf-8")
        except OSError:
            return []
        rows = csv.DictReader(io.StringIO(text))
        return [normalize_symbol(str(row["symbol"])) for row in rows if row.get("symbol")]

    def _connect(self, table: str) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (table,)).fetchone() is None:
            db.close()
            return None
        return db

    def prices_since(self, symbols: list[str], start: str) -> pd.DataFrame:
        """symbol, date, close, adj_close and volume from `start` on, in primary-key order."""
        columns = ["symbol", "date", "close", "adj_close", "volume"]
        db = self._connect("prices")
        if db is None or not symbols:
            if db is not None:
                db.close()
            return pd.DataFrame(columns=columns)
        with closing(db):
            names = {row[1] for row in db.execute("PRAGMA table_info(prices)")}
            adjusted = "adj_close" if "adj_close" in names else "NULL"
            rows: list[tuple] = []
            for offset in range(0, len(symbols), 500):  # Below SQLite's host-parameter limit.
                chunk = symbols[offset:offset + 500]
                marks = ",".join("?" * len(chunk))
                rows += db.execute(f"SELECT symbol,date,close,{adjusted},volume FROM prices WHERE symbol IN ({marks}) "
                                   "AND date>=? ORDER BY symbol,date LIMIT ?",
                                   (*chunk, start, MAX_ROWS + 1 - len(rows))).fetchall()
                if len(rows) > MAX_ROWS:
                    raise ValueError("La ventana de precios del semáforo supera el límite de filas.")
        frame = pd.DataFrame(rows, columns=columns)
        frame["date"] = pd.to_datetime(frame["date"])
        return frame

    def series_since(self, series_id: str, start: str) -> pd.Series:
        db = self._connect("macro_series")
        if db is None:
            return pd.Series(dtype=float)
        with closing(db):
            rows = db.execute("SELECT date,value FROM macro_series WHERE series_id=? AND date>=? AND value IS NOT NULL "
                              "ORDER BY date LIMIT 5000", (series_id, start)).fetchall()
        if not rows:
            return pd.Series(dtype=float)
        return pd.Series([float(value) for _, value in rows], index=pd.to_datetime([day for day, _ in rows]))
