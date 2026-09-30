"""Aggregate estimate capture coverage without initializing or changing SQLite."""

import sqlite3
from contextlib import closing
from pathlib import Path

from gabi.application.errors import QueryError


class SqliteEstimateCaptures:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def coverage(self, period: str, min_symbols: int) -> dict:
        empty = {"batches_total": 0, "batches_eligible": 0,
                 "first_eligible": None, "last_eligible": None}
        if not self.path.is_file():
            return empty
        try:
            db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
            with closing(db):
                db.execute("PRAGMA query_only=ON")
                exists = db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' "
                                    "AND name='estimate_snapshots'").fetchone()
                if exists is None:
                    return empty
                row = db.execute("""
                    WITH batches AS (
                        SELECT captured_at, COUNT(DISTINCT symbol) AS n_symbols
                        FROM estimate_snapshots WHERE period=? GROUP BY captured_at
                    )
                    SELECT COUNT(*),
                           COUNT(CASE WHEN n_symbols >= ? THEN 1 END),
                           MIN(CASE WHEN n_symbols >= ? THEN captured_at END),
                           MAX(CASE WHEN n_symbols >= ? THEN captured_at END)
                    FROM batches
                """, (period, min_symbols, min_symbols, min_symbols)).fetchone()
                return dict(zip(empty, row, strict=True))
        except sqlite3.Error as exc:
            raise QueryError("estimate_data_unavailable", "No se pueden leer las capturas de estimaciones.",
                             503) from exc
