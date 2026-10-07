"""Short operation-scoped connections for the existing FRED tables."""

import sqlite3
from collections.abc import Callable, Sequence
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS macro_series (
    series_id TEXT NOT NULL, date TEXT NOT NULL, value REAL,
    PRIMARY KEY (series_id, date)
);
CREATE TABLE IF NOT EXISTS macro_meta (
    series_id TEXT PRIMARY KEY, fetched_at TEXT NOT NULL
);
"""
ERROR_SCHEMA = """
CREATE TABLE IF NOT EXISTS update_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
    symbol TEXT, reason TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_update_errors_source_time ON update_errors(source, occurred_at);
"""


class SqliteFred:
    def __init__(self, path: Path, clock: Callable[[], datetime], *, max_rows: int = 100000):
        self.path, self.clock, self.max_rows = path, clock, max_rows

    def _read(self, query: str, params: tuple, missing_table: str) -> list:
        if not self.path.is_file():
            return []
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            try:
                return db.execute(query, params).fetchall()
            except sqlite3.OperationalError as exc:
                if str(exc) != f"no such table: {missing_table}":
                    raise
                return []

    @staticmethod
    def _ids(series_ids: Sequence[str]) -> tuple[str, ...]:
        if len(series_ids) > 100:
            raise ValueError("El refresco FRED supera 100 series.")
        return tuple(series_ids)

    def fetched_at(self, series_ids: Sequence[str]) -> dict:
        ids = self._ids(series_ids)
        if not ids:
            return {}
        rows = self._read(f"SELECT series_id,fetched_at FROM macro_meta WHERE series_id IN ({','.join('?' for _ in ids)})",
                          ids, "macro_meta")
        result: dict[str, datetime | None] = {}
        for sid, at in rows:
            try:
                result[sid] = datetime.fromisoformat(at)
            except Exception:
                result[sid] = None
        return result

    def failed(self, series_ids: Sequence[str]) -> set[str]:
        ids = self._ids(series_ids)
        if not ids:
            return set()
        rows = self._read(f"SELECT DISTINCT entity FROM sync_checkpoints WHERE source='fred' "
                          f"AND entity IN ({','.join('?' for _ in ids)}) "
                          "AND json_extract(state_json,'$.status')='failed'", ids, "sync_checkpoints")
        return {row[0] for row in rows}

    def history(self, series_id: str) -> pd.DataFrame:
        rows = self._read("SELECT date,value FROM macro_series WHERE series_id=? ORDER BY date LIMIT ?",
                          (series_id, self.max_rows + 1), "macro_series")
        if len(rows) > self.max_rows:
            raise ValueError("La serie FRED almacenada supera el límite de observaciones.")
        frame = pd.DataFrame(rows, columns=["date", "value"])
        if frame.empty:
            return frame
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.set_index("date")

    def upsert(self, series_id: str, observations: list) -> None:
        if len(observations) > self.max_rows:
            raise ValueError("La escritura FRED supera el límite de observaciones.")
        at = self.clock().isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.executescript(SCHEMA)
            with db:
                db.executemany("INSERT OR REPLACE INTO macro_series VALUES (?,?,?)",
                               [(series_id, day, value) for day, value in observations])
                db.execute("INSERT OR REPLACE INTO macro_meta VALUES (?,?)", (series_id, at))

    def record_errors(self, failed: dict) -> None:
        if not failed:
            return
        at = self.clock().isoformat()
        cutoff = (self.clock() - timedelta(days=90)).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.executescript(ERROR_SCHEMA)
            with db:
                db.executemany("INSERT INTO update_errors(source,symbol,reason,occurred_at) VALUES (?,?,?,?)",
                               [("fred_macro", sid, str(reason), at) for sid, reason in failed.items()])
                db.execute("DELETE FROM update_errors WHERE occurred_at < ?", (cutoff,))
