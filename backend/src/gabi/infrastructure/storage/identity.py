"""Bounded offline identity queries; no schema initialization on reads."""

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd

from gabi.domain.market.identity import normalize_symbol, resolve_claims
from gabi.domain.market.sec_identity import accredited_resolution, resolve_accredited
from gabi.domain.research.periods import P2010, Period
from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only


class SqliteIdentityReads:
    def __init__(self, path: Path, *, periods: tuple[Period, ...] = (P2010,),
                 batch_size: int = 200, max_symbols: int = 1000, max_rows: int = 50000,
                 max_bytes: int = 16 * 1024 * 1024, max_field_bytes: int = 16384):
        self.path, self.periods = path, periods
        self.batch_size, self.max_symbols, self.max_rows = batch_size, max_symbols, max_rows
        self.max_bytes, self.max_field_bytes = max_bytes, max_field_bytes
        if min(batch_size, max_symbols, max_rows, max_bytes, max_field_bytes) <= 0 or batch_size > 200:
            raise ValueError("Invalid identity read limits")

    def _chunks(self, symbols):
        values = list(dict.fromkeys(symbols))
        if len(values) > self.max_symbols:
            raise ValueError("El universo SEC supera el límite de símbolos.")
        for start in range(0, len(values), self.batch_size):
            yield values[start:start + self.batch_size]

    def _read(self):
        return read_only(self.path, self.max_field_bytes)

    def _rows(self, db, query, params):
        return bounded_rows(db, query, params, max_rows=self.max_rows, max_bytes=self.max_bytes,
                            max_field_bytes=self.max_field_bytes)

    def resolve_many(self, symbols: list[str], as_of: str) -> dict[str, dict]:
        day = date.fromisoformat(as_of).isoformat()
        normalized = {symbol: normalize_symbol(symbol) for symbol in symbols}
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

    def registered(self, symbols: list[str]) -> set[str]:
        chunks = list(self._chunks([normalize_symbol(symbol) for symbol in symbols]))
        result: set[str] = set()
        with self._read() as (db, tables):
            if db is not None and "entity_aliases" in tables:
                for chunk in chunks:
                    marks = ",".join("?" for _ in chunk)
                    result.update(row[0] for row in self._rows(db,
                                  f"SELECT DISTINCT symbol FROM entity_aliases WHERE symbol IN ({marks})", chunk))
        return result

    def _observations(self, db, entity_id, dataset):
        rows = self._rows(db, "SELECT symbol,CASE WHEN length(CAST(payload_json AS BLOB))<=? "
                          "THEN payload_json END FROM entity_observations WHERE entity_id=? AND dataset=? "
                          "ORDER BY symbol,record_key", (self.max_field_bytes, entity_id, dataset))
        if any(payload is None for _, payload in rows):
            raise ValueError("La observación de identidad supera el límite de bytes.")
        return pd.DataFrame([{**json.loads(payload), "source_symbol": symbol} for symbol, payload in rows])

    def observations(self, entity_id: str, dataset: str) -> pd.DataFrame:
        with self._read() as (db, tables):
            if db is None or "entity_observations" not in tables:
                return pd.DataFrame()
            return self._observations(db, entity_id, dataset)

    def _aliases(self, db, entity_id):
        return self._rows(db, "SELECT symbol,valid_from,valid_to,confidence FROM entity_aliases WHERE entity_id=?", (entity_id,))

    def aliases(self, entity_id: str) -> list[tuple]:
        with self._read() as (db, tables):
            return self._aliases(db, entity_id) if db is not None and "entity_aliases" in tables else []

    def price_inputs(self, entity_id: str, symbol: str) -> tuple[pd.DataFrame, list[tuple], list[tuple]]:
        with self._read() as (db, tables):
            if db is None or "entity_observations" not in tables:
                return pd.DataFrame(), [], []
            frame = self._observations(db, entity_id, "prices")
            if "entity_aliases" not in tables:
                return frame, [], []
            aliases = self._aliases(db, entity_id)
            conflicts = self._rows(db, "SELECT valid_from,valid_to FROM entity_aliases WHERE symbol=? AND entity_id<>?",
                                   (symbol, entity_id))
            return frame, aliases, conflicts

    def accredited(self, symbols: set[str], as_of: str, interval_source: str) -> dict[str, dict]:
        date.fromisoformat(as_of)
        chunks = list(self._chunks(list(symbols)))
        claims, evidence, intervals = [], [], []
        with self._read() as (db, tables):
            if db is not None:
                for chunk in chunks:
                    marks = ",".join("?" for _ in chunk)
                    if {"entities", "entity_aliases"} <= tables:
                        claims.extend(self._rows(db, "SELECT a.symbol,a.entity_id,e.cik,a.confidence "
                                      "FROM entity_aliases a JOIN entities e USING(entity_id) "
                                      f"WHERE a.symbol IN ({marks}) AND valid_from<=? AND (valid_to IS NULL OR valid_to>?)",
                                      (*chunk, as_of, as_of)))
                    if "entity_observations" in tables:
                        rows = self._rows(db, "SELECT symbol,entity_id,CASE WHEN length(CAST(payload_json AS BLOB))<=? "
                                          "THEN payload_json END,source FROM entity_observations "
                                          f"WHERE dataset='filing_identity' AND symbol IN ({marks}) "
                                          "AND CASE WHEN length(CAST(payload_json AS BLOB))<=? "
                                          "THEN json_extract(payload_json,'$.filed_date')=? ELSE 1 END",
                                          (self.max_field_bytes, *chunk, self.max_field_bytes, as_of))
                        if any(row[2] is None for row in rows):
                            raise ValueError("La evidencia de identidad supera el límite de bytes.")
                        evidence.extend(rows)
                    if "historical_identity_intervals" in tables:
                        intervals.extend(self._rows(db, "SELECT symbol,cik,status,source_id FROM historical_identity_intervals "
                                         f"WHERE symbol IN ({marks}) AND source_id=? AND valid_from<=? AND valid_to>?",
                                         (*chunk, interval_source, as_of, as_of)))
        all_rows = [*claims, *evidence, *intervals]
        if len(all_rows) > self.max_rows or sum(len(value.encode()) for row in all_rows
                                               for value in row if isinstance(value, str)) > self.max_bytes:
            raise ValueError("La identidad acreditada supera el límite de lectura.")
        return resolve_accredited(symbols, as_of, claims, evidence, intervals)

    def filing_dates(self, owners: dict[str, str], legacy: list[str], as_of: str) -> dict[str, str]:
        chunks = list(self._chunks(list(owners.values())))
        ticker_chunks = list(self._chunks(legacy))
        by_owner: dict[str, str] = {}
        result: dict[str, str] = {}
        with self._read() as (db, tables):
            if db is None:
                return result
            if "entity_observations" in tables:
                for chunk in chunks:
                    marks = ",".join("?" for _ in chunk)
                    rows = self._rows(db, "SELECT entity_id,MAX(CASE WHEN length(CAST(payload_json AS BLOB))<=? "
                                      "THEN CASE WHEN json_extract(payload_json,'$.filed_date')<=? "
                                      "THEN json_extract(payload_json,'$.filed_date') END END),"
                                      "MAX(length(CAST(payload_json AS BLOB))>?) FROM entity_observations "
                                      f"WHERE dataset='edgar_facts' AND entity_id IN ({marks}) GROUP BY entity_id",
                                      (self.max_field_bytes, as_of, self.max_field_bytes, *chunk))
                    for owner, day, oversized in rows:
                        if oversized:
                            raise ValueError("La observación de identidad supera el límite de bytes.")
                        if day:
                            by_owner[owner] = day
            result.update({symbol: by_owner[owner] for symbol, owner in owners.items() if owner in by_owner})
            if "edgar_facts" in tables:
                for chunk in ticker_chunks:
                    marks = ",".join("?" for _ in chunk)
                    rows = self._rows(db, f"SELECT symbol,MAX(filed_date) FROM edgar_facts WHERE symbol IN ({marks}) "
                                      "AND filed_date<=? GROUP BY symbol", (*chunk, as_of))
                    result.update({symbol: day for symbol, day in rows if day})
        return result

    def attributed_fingerprint(self) -> str:
        """Explicit evidence operation: stream the unchanged canonical JSON hash."""
        digest = hashlib.sha256()
        digest.update(b"{")
        names = ("entities", "entity_aliases", "entity_candidates", "entity_observations")
        # Evidence hashing may include larger fundamentals payloads than normal
        # query fields. Bound one SQLite row by the operation byte budget,
        # while streaming the total dataset without an aggregate RAM budget.
        with read_only(self.path, max(1, self.max_bytes // 4)) as (db, tables):
            for index, name in enumerate(names):
                if index:
                    digest.update(b", ")
                digest.update((json.dumps(name) + ": [").encode())
                if db is not None and name in tables:
                    for row_index, row in enumerate(db.execute(f"SELECT * FROM {name} ORDER BY 1,2,3")):
                        if row_index:
                            digest.update(b", ")
                        digest.update(json.dumps(row).encode())
                digest.update(b"]")
        digest.update(b"}")
        return digest.hexdigest()
