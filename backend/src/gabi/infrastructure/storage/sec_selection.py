"""Bounded, read-only SEC coverage and dated identity, with operation-owned connections."""

import sqlite3
from collections.abc import Callable
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from gabi.domain.market.identity import resolve_claims
from gabi.domain.market.sec_identity import accredited_resolution, resolve_accredited
from gabi.domain.research.periods import P2010, Period

ERROR_SCHEMA = """
CREATE TABLE IF NOT EXISTS update_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, symbol TEXT,
    reason TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_update_errors_source_time ON update_errors(source,occurred_at);
"""


class SqliteSecSelection:
    def __init__(self, path: Path, now: Callable[[], datetime], *, periods: tuple[Period, ...] = (P2010,),
                 batch_size: int = 200, max_symbols: int = 1000, max_rows: int = 50000,
                 max_bytes: int = 16 * 1024 * 1024, max_field_bytes: int = 16384):
        self.path, self.now, self.periods = path, now, periods
        self.batch_size, self.max_symbols, self.max_rows = batch_size, max_symbols, max_rows
        self.max_bytes, self.max_field_bytes = max_bytes, max_field_bytes
        if min(batch_size, max_symbols, max_rows, max_bytes, max_field_bytes) <= 0 or batch_size > 200:
            raise ValueError("Invalid SEC selection limits")

    def _chunks(self, symbols):
        values = list(dict.fromkeys(symbols))
        if len(values) > self.max_symbols:
            raise ValueError("El universo SEC supera el límite de símbolos.")
        for start in range(0, len(values), self.batch_size):
            yield values[start:start + self.batch_size]

    @contextmanager
    def _read(self):
        if not self.path.is_file():
            yield None, set()
            return
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, max(65536, self.max_field_bytes * 4))
            tables = {name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            yield db, tables

    def _rows(self, db, query, params):
        result: list[tuple] = []
        size = 0
        for row in db.execute(query + " LIMIT ?", (*params, self.max_rows + 1)):
            lengths = [len(value.encode()) for value in row if isinstance(value, str)]
            size += sum(lengths)
            if len(result) >= self.max_rows or size > self.max_bytes or any(n > self.max_field_bytes for n in lengths):
                raise ValueError("La selección SEC supera el límite de lectura.")
            result.append(row)
        return result

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
        day = date.fromisoformat(as_of).isoformat()
        normalized = {symbol: symbol.strip().upper().replace(".", "-") for symbol in symbols}
        groups: dict[str, list[tuple]] = {symbol: [] for symbol in normalized.values()}
        chunks = list(self._chunks(list(groups)))
        period = next((period for period in self.periods if period.covers(day)), None)
        evidence, intervals = [], []
        with self._read() as (db, tables):
            if db is not None:
                for chunk in chunks:
                    marks = ",".join("?" for _ in chunk)
                    if {"entity_aliases", "entities"} <= tables:
                        rows = self._rows(db, "SELECT a.symbol,a.entity_id,e.cik,a.source,a.confidence "
                                          "FROM entity_aliases a JOIN entities e USING(entity_id) "
                                          f"WHERE a.symbol IN ({marks}) AND valid_from<=? AND "
                                          "(valid_to IS NULL OR valid_to>?)", (*chunk, day, day))
                        for symbol, *claim in rows:
                            groups[symbol].append(tuple(claim))
                    fallback = [symbol for symbol in chunk if not groups[symbol]]
                    if not fallback:
                        continue
                    marks = ",".join("?" for _ in fallback)
                    if period is not None and "entity_observations" in tables:
                        rows = self._rows(db, "SELECT symbol,entity_id,CASE WHEN length(CAST(payload_json AS BLOB))<=? "
                                          "THEN payload_json END,source FROM entity_observations "
                                          f"WHERE dataset='filing_identity' AND symbol IN ({marks}) AND "
                                          "CASE WHEN length(CAST(payload_json AS BLOB))<=? THEN "
                                          "json_extract(payload_json,'$.filed_date')=? ELSE 1 END",
                                          (self.max_field_bytes, *fallback, self.max_field_bytes, day))
                        if any(row[2] is None for row in rows):
                            raise ValueError("La evidencia SEC supera el límite de bytes.")
                        evidence.extend(rows)
                    if period is not None and "historical_identity_intervals" in tables:
                        intervals.extend(self._rows(db, "SELECT symbol,cik,status,source_id FROM historical_identity_intervals "
                                         f"WHERE symbol IN ({marks}) AND source_id=? AND valid_from<=? AND valid_to>?",
                                         (*fallback, period.identity_source, day, day)))
        total_rows = [*evidence, *intervals, *(claim for claims in groups.values() for claim in claims)]
        if len(total_rows) > self.max_rows or sum(len(value.encode()) for row in total_rows
                                                for value in row if isinstance(value, str)) > self.max_bytes:
            raise ValueError("La identidad SEC supera el límite de lectura.")
        accredited = resolve_accredited(set(groups), day,
                        [(symbol, claim[0], claim[1], claim[3]) for symbol, claims in groups.items() for claim in claims],
                        evidence, intervals) if period is not None else {}
        resolved = {}
        for original, symbol in normalized.items():
            if not groups[symbol] and period is not None:
                resolved[original] = accredited_resolution(accredited[symbol])
            else:
                row = resolve_claims(groups[symbol], day)
                row.pop("as_of")
                resolved[original] = row
        return resolved

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
