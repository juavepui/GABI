"""Read-only, bounded prices of saved live rankings (a few dozen symbols since their date)."""

import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from gabi.application.errors import QueryError
from gabi.infrastructure.storage.window_prices import SqliteWindowPrices

MAX_SYMBOLS = 101  # Snapshots hold up to 100 candidates, plus SPY.
MAX_ROWS = 400_000


class SqliteSnapshotPrices:
    def __init__(self, data_dir: Path, today: date):
        self.path = data_dir / "gabi.db"
        # Live rankings are prospective, not a reserved history: the window only stops at the data's end.
        self.price_at = SqliteWindowPrices(data_dir, today + timedelta(days=7))

    def _rows(self, sql: str, params: tuple) -> list[tuple]:
        if not self.path.is_file():
            return []
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=30)) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("SELECT 1 FROM sqlite_schema WHERE name='prices'").fetchone() is None:
                    return []
                rows = db.execute(sql, params).fetchmany(MAX_ROWS + 1)
        except sqlite3.Error as exc:
            raise QueryError("data_read_error", "No se pueden consultar los precios locales.", 503) from exc
        if len(rows) > MAX_ROWS:
            raise QueryError("resource_limit", "Los precios del ranking guardado superan el límite de lectura.", 503)
        return rows

    def latest_date(self, symbols: list[str]) -> pd.Timestamp | None:
        """The most recent cached adjusted price among the symbols, as `_latest_cached_date`."""
        if not symbols or len(symbols) > MAX_SYMBOLS:
            return None
        marks = ",".join("?" * len(symbols))
        rows = self._rows(f"SELECT MAX(date) FROM prices WHERE symbol IN ({marks}) AND adj_close IS NOT NULL",
                          tuple(symbols))
        return pd.Timestamp(rows[0][0]) if rows and rows[0][0] else None

    def histories(self, symbols: list[str], as_of_date: str) -> dict[str, pd.DataFrame]:
        """Adjusted closes from a week before the saved date: what `price_curve_for` reads."""
        if len(symbols) > MAX_SYMBOLS:
            raise QueryError("resource_limit", "El ranking guardado tiene demasiadas candidatas.", 503)
        start = (pd.Timestamp(as_of_date) - pd.Timedelta(days=7)).date().isoformat()
        marks = ",".join("?" * len(symbols))
        rows = self._rows(f"SELECT symbol,date,adj_close FROM prices WHERE symbol IN ({marks}) AND date>=? "
                          "ORDER BY symbol,date", (*symbols, start))
        frame = pd.DataFrame(rows, columns=["symbol", "date", "adj_close"])
        frame["date"] = pd.to_datetime(frame["date"])
        return {str(symbol): group.drop(columns="symbol").set_index("date").astype(float)
                for symbol, group in frame.groupby("symbol")}
