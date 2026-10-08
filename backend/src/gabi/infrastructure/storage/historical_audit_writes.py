"""Explicit, transactional persistence of historical audit accreditations."""
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd

from gabi.domain.research.historical_pit import YAHOO_SOURCE
from gabi.domain.research.price_accreditation import _producer, overlap_status
from gabi.infrastructure.storage.historical_archive_schema import SCHEMA as ARCHIVE_SCHEMA
from gabi.infrastructure.storage.historical_write import ensure_entity, initialize, transaction

SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_price_provenance (
 entity_id TEXT NOT NULL, cik TEXT NOT NULL, symbol TEXT NOT NULL,
 valid_from TEXT NOT NULL, valid_to TEXT NOT NULL, source_id TEXT NOT NULL,
 adjustment_basis TEXT NOT NULL, status TEXT NOT NULL, evidence_json TEXT NOT NULL,
 PRIMARY KEY(entity_id,symbol,valid_from,valid_to,source_id),
 CHECK(valid_from < valid_to),
 CHECK(status IN ('tier_a','tier_b','excluded'))
);
CREATE INDEX IF NOT EXISTS idx_historical_price_provenance_lookup
 ON historical_price_provenance(symbol,valid_from,valid_to);
CREATE TABLE IF NOT EXISTS historical_terminal_events (
 entity_id TEXT NOT NULL, symbol TEXT NOT NULL, event_date TEXT NOT NULL,
 event_type TEXT NOT NULL, status TEXT NOT NULL,
 cash_per_share REAL, exchange_ratio REAL, successor_symbol TEXT,
 lower_return REAL, upper_return REAL, evidence_json TEXT NOT NULL,
 PRIMARY KEY(entity_id,symbol,event_date),
 CHECK(status IN ('terminal_return_confirmed','terminal_return_bounded','terminal_return_unknown'))
);
"""

def _adjusted(conn, source_id: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    params: tuple[str, ...]
    if source_id == YAHOO_SOURCE:
        query, params = ("SELECT date,adj_close FROM prices WHERE symbol=? AND date>=? AND date<? ORDER BY date",
                         (symbol, start, end))
    else:
        query, params = ("SELECT date,adj_close FROM historical_prices WHERE source_id=? AND symbol=? "
                         "AND date>=? AND date<? ORDER BY date", (source_id, symbol, start, end))
    frame = pd.read_sql_query(query, conn, params=params)
    frame.index = pd.to_datetime(frame.pop("date"))
    return frame

def _sources_agree(conn, symbol: str, left: str, right: str, start: str, end: str) -> bool:
    status, _count, _p99 = overlap_status(_adjusted(conn, left, symbol, start, end),
                                          _adjusted(conn, right, symbol, start, end))
    return status == "consistent_overlap"

class SqliteHistoricalAuditWrites:
    def __init__(self, path: Path, today: Callable[[], date]):
        self.path, self.today = path, today

    def record_series(self, *, cik, symbol, valid_from, valid_to, source_id,
                      adjustment_basis, status, refs):
        with transaction(self.path) as conn:
            entity_id = ensure_entity(conn, cik, self.today())
            initialize(conn, ARCHIVE_SCHEMA + SCHEMA)
            if status == "tier_b":
                archived = pd.read_sql_query(
                    "SELECT date,adj_close FROM historical_prices WHERE source_id=? AND symbol=? "
                    "AND date>=? AND date<? ORDER BY date", conn,
                    params=(source_id, symbol, valid_from, valid_to)).set_index("date")
                yahoo = pd.read_sql_query(
                    "SELECT date,adj_close FROM prices WHERE symbol=? AND date>=? AND date<? ORDER BY date",
                    conn, params=(symbol, valid_from, valid_to)).set_index("date")
                if archived.empty:
                    raise ValueError("Fallback source has no prices in the accredited interval")
                if not yahoo.empty:
                    archived.index = pd.to_datetime(archived.index)
                    yahoo.index = pd.to_datetime(yahoo.index)
                    overlap, _count, _p99 = overlap_status(yahoo, archived)
                    if overlap in {"divergent_overlap", "divergent_event"}:
                        raise ValueError("Fallback adjusted returns diverge from Yahoo")
            historical_conflict = conn.execute(
                "SELECT 1 FROM historical_identity_intervals WHERE symbol=? AND cik<>? "
                "AND valid_from<? AND valid_to>? LIMIT 1",
                (symbol, cik, valid_to, valid_from)).fetchone()
            if historical_conflict:
                raise ValueError("Historical ticker interval has conflicting CIK evidence")
            conflict = conn.execute(
                "SELECT 1 FROM historical_price_provenance WHERE symbol=? AND entity_id<>? "
                "AND valid_from<? AND valid_to>? AND status!='excluded' LIMIT 1",
                (symbol, entity_id, valid_to, valid_from)).fetchone()
            if conflict:
                raise ValueError("Ticker interval belongs to another issuer")
            competing = conn.execute(
                "SELECT source_id,valid_from,valid_to,evidence_json FROM historical_price_provenance "
                "WHERE symbol=? AND entity_id=? "
                "AND valid_from<? AND valid_to>? AND status!='excluded' "
                "AND NOT (source_id=? AND valid_from=? AND valid_to=?)",
                (symbol, entity_id, valid_to, valid_from, source_id, valid_from, valid_to)).fetchall()
            for other_source, other_from, other_to, other_evidence in competing:
                if other_source == source_id and _producer(other_evidence) not in {None, _producer(refs)}:
                    # The same rows accredited by the audit of another period
                    # (2010-2015 holding into 2016 vs the 2016-2025 trailing window).
                    continue
                # Consecutive trailing windows accredited from different sources
                # overlap. That is allowed only when both sources demonstrably
                # quote the same adjusted returns on the shared span.
                if other_source == source_id or not _sources_agree(
                        conn, symbol, source_id, other_source, max(valid_from, other_from), min(valid_to, other_to)):
                    raise ValueError("Overlapping accredited series require explicit reconciliation")
            conn.execute("INSERT INTO historical_price_provenance VALUES (?,?,?,?,?,?,?,?,?) "
                         "ON CONFLICT(entity_id,symbol,valid_from,valid_to,source_id) DO UPDATE SET "
                         "adjustment_basis=excluded.adjustment_basis,status=excluded.status,"
                         "evidence_json=excluded.evidence_json",
                         (entity_id, cik, symbol, valid_from, valid_to, source_id,
                          adjustment_basis, status, refs))


    def record_terminal(self, **record):
        with transaction(self.path) as conn:
            entity_id = ensure_entity(conn, record['cik'], self.today())
            initialize(conn, SCHEMA)
            self._put_terminal(conn, entity_id, record)


    def remove_producer(self, producer: str) -> int:
        with transaction(self.path) as conn:
            initialize(conn, SCHEMA)
            return conn.execute(
                "DELETE FROM historical_price_provenance WHERE evidence_json LIKE ? OR evidence_json LIKE ?",
                (f'%"producer": "{producer}"%',
                 '%legacy Yahoo cache; original per-row download metadata unavailable%')).rowcount

    def replace_unknown_terminal(self, entity: str, symbol: str, after: str, through: str, record: dict) -> None:
        with transaction(self.path) as conn:
            owner = ensure_entity(conn, record['cik'], self.today())
            initialize(conn, SCHEMA)
            conn.execute("DELETE FROM historical_terminal_events WHERE entity_id=? AND symbol=? AND "
                         "status='terminal_return_unknown' AND event_date>? AND event_date<=?",
                         (entity, symbol, after, through))
            self._put_terminal(conn, owner, record)

    @staticmethod
    def _put_terminal(conn, owner: str, record: dict):
        conn.execute('INSERT INTO historical_terminal_events VALUES (?,?,?,?,?,?,?,?,?,?,?) '
                         'ON CONFLICT(entity_id,symbol,event_date) DO UPDATE SET '
                         'event_type=excluded.event_type,status=excluded.status,'
                         'cash_per_share=excluded.cash_per_share,exchange_ratio=excluded.exchange_ratio,'
                         'successor_symbol=excluded.successor_symbol,lower_return=excluded.lower_return,'
                         'upper_return=excluded.upper_return,evidence_json=excluded.evidence_json',
                         (owner, record['symbol'], record['event_date'], record['event_type'], record['status'],
                          record['cash_per_share'], record['exchange_ratio'], record['successor_symbol'],
                          record['lower_return'], record['upper_return'], record['refs']))
