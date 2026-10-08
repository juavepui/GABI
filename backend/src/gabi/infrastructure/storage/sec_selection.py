"""Bounded, read-only SEC coverage and dated identity, with operation-owned connections."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from gabi.domain.research.periods import P2010, Period
from gabi.infrastructure.storage.identity import SqliteIdentityReads

ERROR_SCHEMA = """
CREATE TABLE IF NOT EXISTS update_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, symbol TEXT,
    reason TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_update_errors_source_time ON update_errors(source,occurred_at);
"""


class SqliteSecSelection(SqliteIdentityReads):
    def __init__(self, path: Path, now: Callable[[], datetime], *, periods: tuple[Period, ...] = (P2010,),
                 batch_size: int = 200, max_symbols: int = 1000, max_rows: int = 50000,
                 max_bytes: int = 16 * 1024 * 1024, max_field_bytes: int = 16384):
        super().__init__(path, periods=periods, batch_size=batch_size, max_symbols=max_symbols,
                         max_rows=max_rows, max_bytes=max_bytes, max_field_bytes=max_field_bytes)
        self.now = now
    def current(self, symbols: list[str]) -> tuple[dict, set[str], dict[str, set[str]]]:
        fetched: dict = {}
        covered: set[str] = set()
        failed: dict[str, set[str]] = {}
        chunks = list(self._chunks(symbols))
        with self._read() as (db, tables):
            if db is None:
                return fetched, covered, failed
            for chunk in chunks:
                marks = ",".join("?" for _ in chunk)
                if "edgar_metrics" in tables:
                    for symbol, at in self._rows(db, f"SELECT symbol,fetched_at FROM edgar_metrics WHERE symbol IN ({marks})", chunk):
                        try:
                            fetched[symbol] = datetime.fromisoformat(at)
                        except (ValueError, TypeError):
                            fetched[symbol] = None
                if "edgar_facts" in tables:
                    covered.update(row[0] for row in self._rows(db,
                                   f"SELECT DISTINCT symbol FROM edgar_facts WHERE symbol IN ({marks})", chunk))
                if "sync_checkpoints" in tables:
                    rows = self._rows(db, "SELECT entity,dataset,CASE WHEN length(CAST(state_json AS BLOB))<=? "
                                      "THEN json_extract(state_json,'$.status') ELSE 'oversized' END "
                                      f"FROM sync_checkpoints WHERE source='sec' AND dataset IN ({marks})",
                                      (self.max_bytes, *(f"facts:{symbol}" for symbol in chunk)))
                    for entity, dataset, status in rows:
                        if status == "oversized":
                            raise ValueError("El checkpoint SEC supera el límite de bytes.")
                        if status == "failed":
                            failed.setdefault(dataset.removeprefix("facts:"), set()).add(entity)
        return fetched, covered, failed

    def covered_entities(self, entities: list[str]) -> set[str]:
        result: set[str] = set()
        chunks = list(self._chunks(entities))
        with self._read() as (db, tables):
            if db is None or "entity_observations" not in tables:
                return result
            for chunk in chunks:
                marks = ",".join("?" for _ in chunk)
                result.update(row[0] for row in self._rows(db, "SELECT DISTINCT entity_id FROM entity_observations "
                              f"WHERE dataset='edgar_facts' AND entity_id IN ({marks})", chunk))
        return result

    def historical(self, symbols: list[str], as_of: str) -> dict[str, dict]:
        return self.resolve_many(symbols, as_of)

    def errors(self, failed: dict) -> None:
        if not failed:
            return
        if len(failed) > self.max_symbols or any(len(str(reason).encode()) > self.max_field_bytes for reason in failed.values()):
            raise ValueError("Los errores SEC superan el límite de escritura.")
        now = self.now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.executescript(ERROR_SCHEMA)
            with db:
                db.executemany("INSERT INTO update_errors(source,symbol,reason,occurred_at) VALUES (?,?,?,?)",
                               [("sec_edgar", symbol, str(reason), now.isoformat()) for symbol, reason in failed.items()])
                db.execute("DELETE FROM update_errors WHERE occurred_at<?", ((now - timedelta(days=90)).isoformat(),))
