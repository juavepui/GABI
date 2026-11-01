"""Issuer-scoped XBRL reads and atomic compatibility/attribution writes."""

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

from gabi.domain.market.identity import require_same_cik
from gabi.domain.market.sec_xbrl import KEYS, normalize_cik
from gabi.infrastructure.storage.identity_writes import ensure_schema, put_facts

FACTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS edgar_facts (
    symbol TEXT NOT NULL, tag TEXT NOT NULL, unit TEXT NOT NULL,
    start_date TEXT NOT NULL, end_date TEXT NOT NULL, val REAL NOT NULL,
    form TEXT, fp TEXT, fy INTEGER, filed_date TEXT, accn TEXT NOT NULL,
    PRIMARY KEY(symbol,tag,unit,start_date,end_date,accn)
);
CREATE INDEX IF NOT EXISTS idx_edgar_facts_symbol_tag ON edgar_facts(symbol,tag);
"""
METRICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS edgar_metrics (
    symbol TEXT PRIMARY KEY, cik TEXT, fetched_at TEXT NOT NULL,
    revenue_cagr_3y REAL, fcf_cagr_3y REAL, roic REAL,
    latest_10k_date TEXT, latest_10k_url TEXT, latest_10q_date TEXT, latest_10q_url TEXT
);
"""
# SEC metrics V2 (#245): the latest annual snapshot of each issuer, computed from its stored facts.
METRICS_V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS sec_metrics_v2 (
    symbol TEXT PRIMARY KEY, cik TEXT, computed_at TEXT NOT NULL, metrics_version TEXT NOT NULL, anchor TEXT,
    roic REAL, roic_state TEXT NOT NULL, roic_reason TEXT, roic_convention TEXT, roic_inputs TEXT NOT NULL,
    total_debt REAL, total_debt_state TEXT NOT NULL, cash REAL, cash_state TEXT NOT NULL
);
"""
SCHEMA = FACTS_SCHEMA + METRICS_SCHEMA
METRICS = ["revenue_cagr_3y", "fcf_cagr_3y", "roic", "latest_10k_date", "latest_10k_url",
           "latest_10q_date", "latest_10q_url", "fetched_at"]
METRICS_V2 = ["symbol", "cik", "computed_at", "metrics_version", "anchor", "roic", "roic_state", "roic_reason",
              "roic_convention", "roic_inputs", "total_debt", "total_debt_state", "cash", "cash_state"]
FACT_COLUMNS = ["tag", "unit", "start_date", "end_date", "val", "form", "fp", "fy", "filed_date", "accn"]


class SqliteXbrl:
    def __init__(self, path: Path, now: Callable[[], datetime], *, max_rows: int = 250000,
                 max_payload_bytes: int = 64 * 1024 * 1024, max_row_bytes: int = 16384):
        self.path, self.now = path, now
        self.max_rows, self.max_payload_bytes, self.max_row_bytes = max_rows, max_payload_bytes, max_row_bytes

    @contextmanager
    def _read(self):
        if not self.path.is_file():
            yield None
            return
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            yield db

    def ensure_entity(self, cik: str) -> str:
        normalized = normalize_cik(cik)
        entity = f"cik:{normalized}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            with db:
                ensure_schema(db)
                existing = db.execute("SELECT cik FROM entities WHERE entity_id=?", (entity,)).fetchone()
                require_same_cik(existing, normalized)
                db.execute("INSERT INTO entities VALUES (?,?,?,?) ON CONFLICT(entity_id) DO NOTHING",
                           (entity, normalized, None, self.now().date().isoformat()))
        return entity

    def has_facts(self, entity: str) -> bool:
        with self._read() as db:
            if db is None:
                return False
            try:
                return bool(db.execute("SELECT 1 FROM entity_observations WHERE entity_id=? "
                                       "AND dataset='edgar_facts' LIMIT 1", (entity,)).fetchone())
            except sqlite3.OperationalError as exc:
                if str(exc) != "no such table: entity_observations":
                    raise
                return False

    def metrics(self, symbol: str) -> dict | None:
        with self._read() as db:
            if db is None:
                return None
            try:
                row = db.execute(f"SELECT {','.join(METRICS)} FROM edgar_metrics WHERE symbol=?",
                                 (symbol,)).fetchone()
            except sqlite3.OperationalError as exc:
                if str(exc) != "no such table: edgar_metrics":
                    raise
                return None
        return dict(zip(METRICS, row)) if row else None

    def facts(self, entity: str) -> pd.DataFrame:
        records: list[dict] = []
        size = 0
        with self._read() as db:
            if db is None:
                return pd.DataFrame()
            try:
                cursor = db.execute("SELECT symbol, CASE WHEN length(CAST(payload_json AS BLOB))<=? "
                                    "THEN payload_json END, length(CAST(payload_json AS BLOB)) "
                                    "FROM entity_observations WHERE entity_id=? AND dataset='edgar_facts' "
                                    "ORDER BY symbol,record_key LIMIT ?",
                                    (self.max_row_bytes, entity, self.max_rows + 1))
            except sqlite3.OperationalError as exc:
                if str(exc) != "no such table: entity_observations":
                    raise
                return pd.DataFrame()
            for symbol, payload, length in cursor:
                size += length
                if length > self.max_row_bytes or size > self.max_payload_bytes or len(records) >= self.max_rows:
                    raise ValueError("El histórico XBRL supera el límite de lectura.")
                records.append({**json.loads(payload), "source_symbol": symbol})
        frame = pd.DataFrame(records)
        return frame.drop_duplicates(KEYS) if not frame.empty else frame

    def save(self, symbol: str, cik: str, rows: list[dict], metrics: dict) -> None:
        if len(rows) > self.max_rows:
            raise ValueError("Los hechos XBRL superan el límite de filas.")
        raw = [json.dumps(row, sort_keys=True, default=str, allow_nan=False).encode() for row in rows]
        if any(len(row) > self.max_row_bytes for row in raw) or sum(map(len, raw)) > self.max_payload_bytes:
            raise ValueError("Los hechos XBRL superan el límite de bytes.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entity = f"cik:{normalize_cik(cik)}"
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            with db:
                for statement in SCHEMA.split(";"):
                    if statement.strip():
                        db.execute(statement)
                if rows:
                    db.executemany(f"INSERT OR REPLACE INTO edgar_facts (symbol,{','.join(FACT_COLUMNS)}) "
                                   "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                   [(symbol, *(r[k] for k in FACT_COLUMNS)) for r in rows])
                    put_facts(db, entity, symbol, rows,
                              f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalize_cik(cik)}.json")
                db.execute(f"INSERT OR REPLACE INTO edgar_metrics (symbol,cik,fetched_at,{','.join(METRICS[:-1])}) "
                           "VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (symbol, cik, self.now().isoformat(), *(metrics.get(k) for k in METRICS[:-1])))

    def _write(self, schema: str):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(schema)
        return closing(db)

    def store_facts(self, symbol: str, rows: list[dict], *, entity: str | None = None, cik: str | None = None) -> None:
        """Ticker-keyed facts, and their issuer attribution when ``entity`` is given, in one commit."""
        if not rows:
            return
        with self._write(FACTS_SCHEMA) as db:
            db.executemany(f"INSERT OR REPLACE INTO edgar_facts (symbol,{','.join(FACT_COLUMNS)}) "
                           "VALUES (?,?,?,?,?,?,?,?,?,?,?)", [(symbol, *(r[k] for k in FACT_COLUMNS)) for r in rows])
            if entity is not None and cik is not None:
                put_facts(db, entity, symbol, rows,
                          f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalize_cik(cik)}.json")
            db.commit()

    def store_metrics(self, symbol: str, cik: str, metrics: dict) -> None:
        with self._write(METRICS_SCHEMA) as db:
            db.execute(f"INSERT OR REPLACE INTO edgar_metrics (symbol,cik,fetched_at,{','.join(METRICS[:-1])}) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (symbol, cik, self.now().isoformat(), *(metrics.get(k) for k in METRICS[:-1])))
            db.commit()

    def save_metrics_v2(self, symbol: str, cik: str | None, row: dict) -> None:
        """One issuer's SEC metrics V2 (#245) in their own table; V1 and the facts are not touched."""
        values = {**{column: row.get(column) for column in METRICS_V2[3:]},
                  "roic_inputs": json.dumps(row.get("roic_inputs") or [], sort_keys=True, allow_nan=False)}
        with self._write(METRICS_V2_SCHEMA) as db:
            db.execute(f"INSERT OR REPLACE INTO sec_metrics_v2 ({','.join(METRICS_V2)}) "
                       f"VALUES ({','.join('?' * len(METRICS_V2))})",
                       (symbol, cik, self.now().isoformat(), *(values[column] for column in METRICS_V2[3:])))
            db.commit()

    def metrics_v2_state(self, symbols: list[str]) -> dict[str, tuple[str | None, str | None]]:
        """Stored CIK and V2 version of each symbol with V1 metrics: what a V2 fill needs, in one query."""
        if not symbols:
            return {}
        with self._read() as db:
            if db is None:
                return {}
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            if "edgar_metrics" not in tables:
                return {}
            version = "v.metrics_version" if "sec_metrics_v2" in tables else "NULL"
            join = " LEFT JOIN sec_metrics_v2 v USING(symbol)" if "sec_metrics_v2" in tables else ""
            placeholders = ",".join("?" * len(symbols))
            rows = db.execute(f"SELECT m.symbol, m.cik, {version} FROM edgar_metrics m{join} "
                              f"WHERE m.symbol IN ({placeholders})", tuple(symbols)).fetchall()
        return {symbol: (cik, stored) for symbol, cik, stored in rows}
