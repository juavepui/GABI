"""Bounded SEC fact queries on operation-owned read-only SQLite connections."""

import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

import pandas as pd

from gabi.domain.market.sec_xbrl import KEYS

FACT_COLUMNS = ["symbol", "tag", "unit", "start_date", "end_date", "val", "form", "fp", "fy", "filed_date", "accn"]
METRIC_COLUMNS = ["revenue_cagr_3y", "fcf_cagr_3y", "roic", "latest_10k_date", "latest_10k_url",
                  "latest_10q_date", "latest_10q_url", "fetched_at"]


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

    def issuer_facts(self, symbol: str, *, tags: list[str] | None = None, as_of: str | None = None,
                     unit: str | None = None) -> pd.DataFrame:
        """Facts of the symbol's SEC entity, whichever alias stored them (#170).

        The sync writes to edgar_facts, under the current symbol, only the rows its entity did
        not know yet: an issuer whose history was stored under an old ticker or a historical
        CIK key keeps the rest there. The entity's observations hold the whole history. Without
        a stored CIK, the symbol's own rows are read."""
        with self._read() as (db, tables):
            found = (self._rows(db, "SELECT cik FROM edgar_metrics WHERE symbol=?", (symbol,))
                     if db is not None and "edgar_metrics" in tables else [])
        cik = str(found[0][0]).strip() if found and found[0][0] else None
        if cik and cik.isdigit():
            frame = self.facts(symbol, entity_id=f"cik:{int(cik):010d}", tags=tags, as_of=as_of, unit=unit)
            if not frame.empty:
                return frame.drop(columns=["source_symbol"]).assign(symbol=symbol)
        return self.facts(symbol, tags=tags, as_of=as_of, unit=unit)

    def issuer(self, cik: str, as_of: str) -> pd.DataFrame:
        with self._read() as (db, tables):
            if db is None or "entity_observations" not in tables:
                return pd.DataFrame()
            rows = self._observations(db, f"cik:{cik}", issuer_cutoff=as_of)
        return pd.DataFrame([{**json.loads(payload), "source_url": source} for symbol, payload, source in rows])

    def issuer_inputs(self, cik: str, as_of: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        # One SELECT owns both views, so a concurrent commit cannot mix revisions.
        with self._read() as (db, tables):
            if db is None or "entity_observations" not in tables:
                return pd.DataFrame(), pd.DataFrame()
            rows = self._observations(db, f"cik:{cik}")
        decoded = [(symbol, json.loads(payload), source) for symbol, payload, source in rows]
        raw = pd.DataFrame([{**record, "source_symbol": symbol} for symbol, record, source in decoded])
        versions = pd.DataFrame([{**record, "source_url": source} for symbol, record, source in decoded])
        if not raw.empty:
            raw = raw.drop_duplicates(KEYS)
            raw = raw[raw.filed_date.notna() & (raw.filed_date <= as_of)]
            versions = versions[versions.filed_date.notna() & (versions.filed_date <= as_of)
                                & versions.end_date.notna() & (versions.end_date <= as_of)]
        return versions, raw

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

    def _by_symbol(self, table: str, columns: str, symbols: list[str], *, distinct: bool = False) -> list[tuple]:
        # Both tables key rows by symbol (PK or DISTINCT), so each batch returns at most its size.
        symbols = list(dict.fromkeys(symbols))
        if not symbols:
            return []
        rows: list[tuple] = []
        with self._read() as (db, tables):
            if db is None or table not in tables:
                return rows
            db.execute("BEGIN")  # every batch observes one revision
            for start in range(0, len(symbols), self.batch_size):
                chunk = symbols[start:start + self.batch_size]
                rows += self._rows(db, f"SELECT {'DISTINCT ' if distinct else ''}{columns} FROM {table} "
                                   "WHERE symbol IN (" + ",".join("?" for _ in chunk) + ")", tuple(chunk))
        return rows

    def cached_metrics(self, symbols: list[str]) -> dict[str, dict]:
        rows = self._by_symbol("edgar_metrics", "symbol," + ",".join(METRIC_COLUMNS), symbols)
        return {row[0]: dict(zip(METRIC_COLUMNS, row[1:])) for row in rows}

    def fetched_at(self, symbols: list[str]) -> dict[str, object]:
        return dict(self._by_symbol("edgar_metrics", "symbol,fetched_at", symbols))

    def stored_ciks(self) -> dict[str, str]:
        """Every cached symbol→CIK pair, bounded by the row budget."""
        with self._read() as (db, tables):
            if db is None or "edgar_metrics" not in tables:
                return {}
            return dict(self._rows(db, "SELECT symbol,cik FROM edgar_metrics"))

    def symbols_with_facts(self, symbols: list[str]) -> set[str]:
        """Symbols with dated facts under their own rows or under their stored CIK's entity (#201).

        A symbol whose whole history was stored under a former alias has no rows of its own:
        reading only by symbol marked it uncovered and re-downloaded it on every update."""
        symbols = list(dict.fromkeys(symbols))
        covered: set[str] = set()
        with self._read() as (db, tables):
            if db is None or "edgar_facts" not in tables:
                return covered
            db.execute("BEGIN")  # every batch observes one revision

            def batches(sql, values):
                for start in range(0, len(values), self.batch_size):
                    chunk = values[start:start + self.batch_size]
                    yield from self._rows(db, sql.format(",".join("?" for _ in chunk)), tuple(chunk))

            covered.update(symbol for symbol, in batches("SELECT DISTINCT symbol FROM edgar_facts WHERE symbol IN ({})",
                                                         symbols))
            if not {"edgar_metrics", "entity_observations"} <= tables:
                return covered
            owners: dict[str, list[str]] = {}
            for symbol, cik in batches("SELECT symbol,cik FROM edgar_metrics WHERE symbol IN ({})",
                                       [symbol for symbol in symbols if symbol not in covered]):
                cik = str(cik).strip() if cik else ""
                if cik.isdigit():
                    owners.setdefault(f"cik:{int(cik):010d}", []).append(symbol)
            for entity, in batches("SELECT DISTINCT entity_id FROM entity_observations "
                                   "WHERE dataset='edgar_facts' AND entity_id IN ({})", list(owners)):
                covered.update(owners[entity])
        return covered
