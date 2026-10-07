"""Bounded SEC fact queries on operation-owned read-only SQLite connections."""

import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

import pandas as pd

from gabi.domain.market.sec_xbrl import KEYS

FACT_COLUMNS = ["symbol", "tag", "unit", "start_date", "end_date", "val", "form", "fp", "fy", "filed_date", "accn"]


class SqliteSecReads:
    def __init__(self, path: Path, *, max_rows: int = 250000, max_bytes: int = 64 * 1024 * 1024,
                 max_row_bytes: int = 16384, max_symbols: int = 1000, batch_size: int = 200):
        self.path = path
        self.max_rows, self.max_bytes, self.max_row_bytes = max_rows, max_bytes, max_row_bytes
        self.max_symbols, self.batch_size = max_symbols, batch_size
        if min(max_rows, max_bytes, max_row_bytes, max_symbols, batch_size) < 1 or batch_size > 200:
            raise ValueError("Invalid SEC read limits")

    @contextmanager
    def _read(self):
        if not self.path.is_file():
            yield None, set()
            return
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, max(65536, self.max_row_bytes * 4))
            tables = {name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            yield db, tables

    def _rows(self, db, sql, params=()):
        rows: list[tuple] = []
        size = 0
        try:
            for row in db.execute(sql + " LIMIT ?", (*params, self.max_rows + 1)):
                length = sum(len(value.encode()) if isinstance(value, str) else 8 for value in row)
                size += length
                if len(rows) >= self.max_rows or size > self.max_bytes or length > self.max_row_bytes:
                    raise ValueError("Los hechos SEC superan el límite de lectura.")
                rows.append(row)
        except sqlite3.DataError as exc:
            if exc.sqlite_errorcode != sqlite3.SQLITE_TOOBIG:
                raise
            raise ValueError("El registro SEC supera el límite de SQLite.") from exc
        return rows

    def _observations(self, db, entity, *, issuer_cutoff=None):
        # Guard before decoding JSON, including malformed/oversized source payloads.
        sql = ("SELECT symbol,CASE WHEN length(CAST(payload_json AS BLOB))<=? THEN payload_json END,source "
               "FROM entity_observations WHERE entity_id=? AND dataset='edgar_facts'")
        params: tuple = (self.max_row_bytes, entity)
        if issuer_cutoff:
            sql += (" AND CASE WHEN length(CAST(payload_json AS BLOB))<=? THEN "
                    "json_extract(payload_json,'$.filed_date')<=? AND json_extract(payload_json,'$.end_date')<=? ELSE 1 END")
            params += (self.max_row_bytes, issuer_cutoff, issuer_cutoff)
        sql += " ORDER BY symbol,record_key"
        rows = self._rows(db, sql, params)
        if any(payload is None for symbol, payload, source in rows):
            raise ValueError("El JSON SEC supera el límite de lectura.")
        return rows

    def facts(self, symbol: str, *, entity_id: str | None = None, tags: list[str] | None = None,
              as_of: str | None = None, unit: str | None = None) -> pd.DataFrame:
        if tags and len(tags) > 200:
            raise ValueError("Los tags SEC superan el límite de consulta.")
        with self._read() as (db, tables):
            if entity_id:
                if db is None or "entity_observations" not in tables:
                    return pd.DataFrame()
                rows = self._observations(db, entity_id)
                frame = pd.DataFrame([{**json.loads(payload), "source_symbol": symbol}
                                      for symbol, payload, source in rows])
                if frame.empty:
                    return frame
                # Duplicate attribution picks the first alias before date filtering,
                # exactly as the published issuer reader did.
                if tags:
                    frame = frame[frame.tag.isin(tags)]
                frame = frame.drop_duplicates(KEYS)
            else:
                if db is None or "edgar_facts" not in tables:
                    return pd.DataFrame(columns=FACT_COLUMNS)
                sql = "SELECT " + ",".join(FACT_COLUMNS) + " FROM edgar_facts WHERE symbol=?"
                params: tuple = (symbol,)
                if tags:
                    sql += " AND tag IN (" + ",".join("?" for _ in tags) + ")"
                    params += tuple(tags)
                if as_of:
                    sql += " AND filed_date<=?"
                    params += (as_of,)
                if unit:
                    sql += " AND unit=?"
                    params += (unit,)
                frame = pd.DataFrame(self._rows(db, sql + " ORDER BY end_date,filed_date", params), columns=FACT_COLUMNS)
        if as_of and not frame.empty:
            frame = frame[frame.filed_date.notna() & (frame.filed_date <= as_of)]
        if unit and not frame.empty:
            frame = frame[frame.unit == unit]
        return frame

    def issuer(self, cik: str, as_of: str) -> pd.DataFrame:
        with self._read() as (db, tables):
            if db is None or "entity_observations" not in tables:
                return pd.DataFrame()
            rows = self._observations(db, f"cik:{cik}", issuer_cutoff=as_of)
        return pd.DataFrame([{**json.loads(payload), "source_url": source} for symbol, payload, source in rows])

    def last_filed(self, symbols: list[str], as_of: str | None = None) -> dict[str, str]:
        symbols = list(dict.fromkeys(symbols))
        if len(symbols) > self.max_symbols:
            raise ValueError("Los símbolos SEC superan el límite de consulta.")
        result: dict[str, str] = {}
        with self._read() as (db, tables):
            if db is None or "edgar_facts" not in tables:
                return result
            for start in range(0, len(symbols), self.batch_size):
                chunk = symbols[start:start + self.batch_size]
                sql = "SELECT symbol,MAX(filed_date) FROM edgar_facts WHERE symbol IN (" + ",".join("?" for _ in chunk) + ")"
                params = tuple(chunk)
                if as_of:
                    sql += " AND filed_date<=?"
                    params += (as_of,)
                result.update({symbol: day for symbol, day in self._rows(db, sql + " GROUP BY symbol", params) if day})
        return result
