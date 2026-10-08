"""Read accredited price intervals and terminal events without schema writes."""

import json
from pathlib import Path

import pandas as pd

from gabi.domain.research.historical_pit import ADJUSTED, YAHOO_SOURCE
from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only


class SqliteHistoricalPit:
    def __init__(self, path: Path, *, max_rows: int = 25000, max_bytes: int = 16 * 1024 * 1024,
                 max_field_bytes: int = 1024 * 1024):
        if min(max_rows, max_bytes, max_field_bytes) <= 0:
            raise ValueError("Invalid historical price read limits")
        self.path, self.max_rows = path, max_rows
        self.max_bytes, self.max_field_bytes = max_bytes, max_field_bytes

    def _rows(self, db, query, params):
        return bounded_rows(db, query, params, max_rows=self.max_rows, max_bytes=self.max_bytes,
                            max_field_bytes=self.max_field_bytes)

    def provenance(self, entity_id: str) -> list[tuple]:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "historical_price_provenance" not in tables:
                return []
            rows = self._rows(db, "SELECT source_id,symbol,valid_from,valid_to,status,evidence_json "
                              "FROM historical_price_provenance WHERE entity_id=? "
                              "AND status IN ('tier_a','tier_b') AND adjustment_basis=?", (entity_id, ADJUSTED))
        return [(*row[:-1], json.loads(row[-1])) for row in rows]

    def windows(self, entity_id: str, source_id: str, symbol: str, start: str, end: str) -> list[dict] | None:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "historical_price_provenance" not in tables:
                return None
            rows = self._rows(db, "SELECT evidence_json FROM historical_price_provenance WHERE entity_id=? AND source_id=? "
                              "AND symbol=? AND valid_from=? AND valid_to=?", (entity_id, source_id, symbol, start, end))
        if not rows:
            return None
        refs = [ref for ref in json.loads(rows[0][0]) if ref.get("kind") == "accredited_windows"]
        return refs[0]["windows"] if refs else None

    def prices(self, source_id: str, symbol: str, start: str, end: str) -> pd.DataFrame:
        columns = ["date", "close", "adj_close"]
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            table = "prices" if source_id == YAHOO_SOURCE else "historical_prices"
            rows = []
            if db is not None and table in tables:
                source_clause = "" if source_id == YAHOO_SOURCE else "source_id=? AND "
                params = (symbol, start, end) if source_id == YAHOO_SOURCE else (source_id, symbol, start, end)
                rows = self._rows(db, f"SELECT date,close,adj_close FROM {table} WHERE {source_clause}"
                                  "symbol=? AND date>=? AND date<? ORDER BY date", params)
        frame = pd.DataFrame(rows, columns=columns)
        # pd.read_sql_query inferred float for nullable numeric columns; preserve
        # that behavior, including empty dated frames.
        frame.index = pd.to_datetime(frame.pop("date"))
        return frame[(frame["adj_close"] > 0) & (frame["close"] > 0)]

    def terminal_event(self, entity_id: str, start: str, end: str) -> dict | None:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "historical_terminal_events" not in tables:
                return None
            rows = self._rows(db, "SELECT * FROM (SELECT event_date,event_type,status,cash_per_share,exchange_ratio "
                              "FROM historical_terminal_events WHERE entity_id=? AND event_date>? AND event_date<=? "
                              "ORDER BY event_date LIMIT 1)", (entity_id, start[:10], end[:10]))
        return dict(zip(("event_date", "event_type", "status", "cash_per_share", "exchange_ratio"), rows[0], strict=True)) if rows else None

    def split_factor(self, symbol: str, as_of: str) -> float:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            rows = self._rows(db, "SELECT ratio FROM splits WHERE symbol=? AND date>?", (symbol, as_of)) \
                if db is not None and "splits" in tables else []
        factor = 1.0
        for ratio, in rows:
            if ratio:
                factor *= ratio
        return factor
