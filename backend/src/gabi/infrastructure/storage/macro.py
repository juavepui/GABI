"""Bounded read-only queries over the existing FRED cache."""

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path


class SqliteMacro:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def value_at_or_before(self, series_id: str, cutoff: date | None) -> tuple[date, float] | None:
        if not self.path.is_file():
            return None
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name='macro_series'").fetchone() is None:
                return None
            if cutoff is None:
                row = db.execute("SELECT date,value FROM macro_series WHERE series_id=? AND value IS NOT NULL "
                                 "ORDER BY date DESC LIMIT 1", (series_id,)).fetchone()
            else:
                row = db.execute("SELECT date,value FROM macro_series WHERE series_id=? AND date<=? "
                                 "AND value IS NOT NULL ORDER BY date DESC LIMIT 1",
                                 (series_id, cutoff.isoformat())).fetchone()
            return (date.fromisoformat(row[0]), float(row[1])) if row else None
