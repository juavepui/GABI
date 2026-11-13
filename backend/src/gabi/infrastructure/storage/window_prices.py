"""Read-only adjusted prices around one date, never past the observed cut."""

import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from gabi.application.errors import QueryError

WINDOW = pd.Timedelta(days=7)  # Tolerance of evaluation._adjusted_at, reproduced exactly.


class SqliteWindowPrices:
    """`price_at(symbol, target, after)` with the legacy semantics and a bounded SQL window."""

    def __init__(self, data_dir: Path, cutoff: date):
        self.path = data_dir / "gabi.db"
        self.cutoff = cutoff

    def __call__(self, symbol: str, target: pd.Timestamp, after: bool = False) -> float | None:
        first, last = (target, target + WINDOW) if after else (target - WINDOW, target)
        if last.date() > self.cutoff:
            raise QueryError("reserved_period", "La ventana de precios supera el periodo observado.", 403)
        if not self.path.is_file():
            return None
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=30)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute(
                "SELECT date, adj_close FROM prices WHERE symbol=? AND date>=? AND date<? ORDER BY date",
                (symbol, first.date().isoformat(), (last.date() + timedelta(days=1)).isoformat()),
            ).fetchall()
        if not rows:
            return None
        values = pd.Series([row[1] for row in rows], index=pd.to_datetime([row[0] for row in rows]),
                           dtype=float).dropna()
        if after:
            values = values[(values.index >= target) & (values.index <= target + WINDOW)]
            return float(values.iloc[0]) if not values.empty else None
        values = values[(values.index <= target) & (values.index >= target - WINDOW)]
        return float(values.iloc[-1]) if not values.empty else None
