"""Versioned historical source data, kept separate from operational Yahoo series.

Research archives can use different split conventions and reused tickers. Their
rows are queryable here without silently replacing the operational price cache.
"""
import json

import numpy as np
import pandas as pd

from . import identity, storage

IDENTITY_INTERVAL_SOURCE = "sec-identity-evidence:2010-2015:v1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_sources (
 source_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historical_membership (
 source_id TEXT NOT NULL, date TEXT NOT NULL, tickers TEXT NOT NULL,
 PRIMARY KEY(source_id,date)
);
CREATE TABLE IF NOT EXISTS historical_issuer_candidates (
 source_id TEXT NOT NULL, symbol TEXT NOT NULL, cik TEXT NOT NULL,
 name TEXT, date_added TEXT, date_removed TEXT, observed_from TEXT,
 PRIMARY KEY(source_id,symbol,cik,date_added,observed_from)
);
CREATE TABLE IF NOT EXISTS historical_prices (
 source_id TEXT NOT NULL, symbol TEXT NOT NULL, date TEXT NOT NULL,
 open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL,
 close_basis TEXT NOT NULL,
 PRIMARY KEY(source_id,symbol,date)
);
CREATE TABLE IF NOT EXISTS historical_facts (
 source_id TEXT NOT NULL, candidate_symbol TEXT NOT NULL, cik TEXT NOT NULL,
 record_key TEXT NOT NULL, filed_date TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(source_id,candidate_symbol,cik,record_key)
);
CREATE TABLE IF NOT EXISTS historical_identity_intervals (
 source_id TEXT NOT NULL, symbol TEXT NOT NULL, cik TEXT NOT NULL,
 valid_from TEXT NOT NULL, valid_to TEXT NOT NULL,
 status TEXT NOT NULL, evidence_count INTEGER NOT NULL,
 first_filed TEXT, last_filed TEXT, source_refs_json TEXT NOT NULL,
 PRIMARY KEY(source_id,symbol,cik,valid_from,valid_to)
);
CREATE INDEX IF NOT EXISTS idx_historical_identity_interval_symbol
 ON historical_identity_intervals(symbol,valid_from,valid_to);
"""


def register_source(source_id: str, metadata: dict):
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR REPLACE INTO historical_sources VALUES (?,?)",
                     (source_id, json.dumps(metadata, sort_keys=True)))
        conn.commit()


def import_membership(source_id: str, frame: pd.DataFrame, start: str, end: str) -> int:
    selected = frame[(frame["date"] >= start) & (frame["date"] < end)].copy()
    dates = pd.to_datetime(selected["date"], format="%Y-%m-%d", errors="raise")
    if dates.duplicated().any():
        raise ValueError("Conflicting/duplicate source snapshot dates require review")
    rows = []
    for row in selected.itertuples(index=False):
        members = sorted({s.strip().replace(".", "-") for s in row.tickers.split(",") if s.strip()})
        if not members:
            raise ValueError("Empty source membership")
        rows.append((source_id, row.date, ",".join(members)))
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT OR REPLACE INTO historical_membership VALUES (?,?,?)", rows)
        conn.commit()
    return len(rows)


def get_membership(source_id: str, as_of: str) -> dict:
    """Source-specific membership; does not assert a complete or verified universe."""
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        metadata = conn.execute("SELECT metadata_json FROM historical_sources WHERE source_id=?", (source_id,)).fetchone()
        if not metadata:
            raise ValueError("Unknown historical source")
        details = json.loads(metadata[0])
        if not details["start"] <= as_of < details["end_exclusive"]:
            raise ValueError("Date outside imported source coverage")
        row = conn.execute("SELECT date,tickers FROM historical_membership WHERE source_id=? AND date<=? "
                           "ORDER BY date DESC LIMIT 1", (source_id, as_of)).fetchone()
    if row is None:
        raise ValueError("No source snapshot at this date")
    return {"symbols": row[1].split(","), "source_date": row[0], "source_id": source_id,
            "quality": "community_unverified", "metadata": details}


def import_issuer_candidates(source_id: str, frame: pd.DataFrame) -> int:
    records = []
    for row in frame.fillna("").itertuples(index=False):
        if row.cik:
            records.append((source_id, row.symbol.replace(".", "-"), row.cik.zfill(10), row.name,
                            row.date_added, row.date_removed, row.created_at))
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT OR REPLACE INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)", records)
        conn.commit()
    return len(records)


def import_price_chunk(source_id: str, frame: pd.DataFrame, symbols: set[str], start: str, end: str) -> dict:
    frame = frame.rename(columns={"adjusted_close": "adj_close"}).copy()
    frame["symbol"] = frame["symbol"].str.replace(".", "-", regex=False)
    frame = frame[(frame["date"] >= start) & (frame["date"] < end) & frame["symbol"].isin(symbols)]
    pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="raise")
    columns = ["open", "high", "low", "close", "adj_close", "volume"]
    values = frame[columns].apply(pd.to_numeric, errors="coerce")
    valid = np.isfinite(values).all(axis=1) & (values[columns[:-1]] > 0).all(axis=1) & (values["volume"] >= 0)
    valid &= values["high"] + 0.001 >= values[["open", "close", "low"]].max(axis=1)
    valid &= values["low"] - 0.001 <= values[["open", "close", "high"]].min(axis=1)
    rejected = int((~valid).sum())
    frame[columns] = values
    frame = frame[valid]
    if frame.duplicated(["symbol", "date"]).any():
        raise ValueError("Duplicate price observations within source chunk")
    records = [(source_id, row.symbol, row.date, row.open, row.high, row.low, row.close, row.adj_close,
                row.volume, "as_traded") for row in frame.itertuples(index=False)]
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        # Rerunning a pinned source is idempotent; a new revision uses a new ID.
        conn.executemany("INSERT OR IGNORE INTO historical_prices VALUES (?,?,?,?,?,?,?,?,?,?)", records)
        conn.commit()
    return {"accepted": len(records), "rejected": rejected}


def get_prices(source_id: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        frame = pd.read_sql_query("SELECT date,open,high,low,close,adj_close,volume,close_basis "
                                  "FROM historical_prices WHERE source_id=? AND symbol=? AND date>=? AND date<? "
                                  "ORDER BY date", conn, params=(source_id, symbol.replace(".", "-"), start, end))
    frame["date"] = pd.to_datetime(frame["date"])
    result = frame.set_index("date")
    result.attrs.update(source_id=source_id, identity_status="unverified", close_basis="as_traded")
    return result


def import_sec_facts(source_id: str, candidate_symbol: str, cik: str, rows: list[dict], *, source_url: str | None = None) -> int:
    """SEC verifies the issuer of facts, not a community ticker-to-issuer mapping.

    Keep candidate provenance and issuer observations, without populating the
    legacy symbol cache or activating a historical alias.
    """
    entity_id = identity.ensure_entity(cik)
    cik = identity.normalize_cik(cik)
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        records = [(source_id, candidate_symbol, cik,
                    json.dumps([r.get(k, "") for k in identity.DATA_KEYS["edgar_facts"]]),
                    r["filed_date"], json.dumps(r, allow_nan=False)) for r in rows]
        conn.executemany("INSERT OR REPLACE INTO historical_facts VALUES (?,?,?,?,?,?)", records)
        identity.put_observations(conn, entity_id, "edgar_facts", candidate_symbol, rows,
                                  source_url or f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        conn.commit()
    return len(records)


def import_filing_identity_evidence(rows: list[dict]) -> int:
    """Store original SEC ticker/CIK observations without activating aliases.

    The XBRL cover proves the relationship on its filing date only. Importing
    these observations must not make legacy ticker prices available to a new
    issuer or imply a continuous ticker interval.
    """
    count = 0
    for row in rows:
        if not str(row["source_url"]).startswith("https://www.sec.gov/Archives/edgar/data/"):
            raise ValueError("Original SEC filing URL required")
        if len(str(row["sha256"])) != 64:
            raise ValueError("Original SEC filing SHA-256 required")
        pd.Timestamp(row["filed_date"])
        entity_id = identity.ensure_entity(row["cik"])
        symbol = identity.normalize_symbol(row["symbol"])
        payload = {"accession": row["accession"], "filed_date": row["filed_date"],
                   "historical_name": row.get("historical_name"), "sha256": row["sha256"],
                   "historical_name_source": row.get("historical_name_source"),
                   "source_url": row["source_url"]}
        with storage.get_connection() as conn:
            identity.put_observations(conn, entity_id, "filing_identity", symbol,
                                      [payload], row["source_url"])
            conn.commit()
        count += 1
    return count


def get_filing_identity_evidence(symbol: str, as_of: str) -> dict:
    """Resolve SEC filing-day evidence only; other dates remain unproven."""
    day = pd.Timestamp(as_of).date().isoformat()
    with storage.get_connection() as conn:
        identity.ensure_schema(conn)
        rows = conn.execute("SELECT entity_id,payload_json,source FROM entity_observations "
                            "WHERE dataset='filing_identity' AND symbol=?",
                            (identity.normalize_symbol(symbol),)).fetchall()
    matches = [(entity_id, json.loads(payload), source) for entity_id, payload, source in rows
               if json.loads(payload).get("filed_date") == day]
    entities = {row[0] for row in matches}
    if len(entities) != 1:
        return {"status": "ambiguous" if entities else "unresolved", "entity_id": None,
                "cik": None, "evidence": [row[1] for row in matches]}
    entity_id = next(iter(entities))
    return {"status": "resolved", "entity_id": entity_id, "cik": entity_id.removeprefix("cik:"),
            "evidence": [row[1] for row in matches]}


def replace_identity_intervals(source_id: str, rows: list[dict]) -> int:
    """Replace one reproducible research tier; never activate operational aliases."""
    allowed = {"confirmed_by_multiple_evidence", "corroborated_candidate",
               "ambiguous", "unresolved"}
    records = []
    for row in rows:
        if row["status"] not in allowed:
            raise ValueError("Unknown historical identity tier")
        start, end = row["valid_from"], row["valid_to"]
        if start >= end:
            raise ValueError("Invalid historical identity interval")
        records.append((source_id, identity.normalize_symbol(row["symbol"]),
                        identity.normalize_cik(row["cik"]), start, end, row["status"],
                        row["evidence_count"], row.get("first_filed"), row.get("last_filed"),
                        json.dumps(row.get("source_refs", []), sort_keys=True)))
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM historical_identity_intervals WHERE source_id=?", (source_id,))
        conn.executemany("INSERT INTO historical_identity_intervals VALUES (?,?,?,?,?,?,?,?,?,?)", records)
        conn.commit()
    return len(records)


def source_summary() -> list[dict]:
    """Local archive coverage, independent of live-universe data quality."""
    with storage.get_connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='historical_sources'").fetchone():
            return []
        result = []
        for table, kind in [("historical_membership", "Composición"), ("historical_prices", "Precios")]:
            for sid, count, first, last in conn.execute(
                    f"SELECT source_id,COUNT(*),MIN(date),MAX(date) FROM {table} GROUP BY source_id"):
                result.append({"Fuente": sid, "Datos": kind, "Filas": count, "Desde": first, "Hasta": last})
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='historical_facts'").fetchone():
            for sid, count, first, last in conn.execute(
                    "SELECT source_id,COUNT(*),MIN(filed_date),MAX(filed_date) FROM historical_facts GROUP BY source_id"):
                result.append({"Fuente": sid, "Datos": "Fundamentales SEC por CIK", "Filas": count,
                               "Desde": first, "Hasta": last})
    return result


def unique_historical_ciks(frame: pd.DataFrame, targets: set[str], live: dict, stored: dict) -> tuple[dict, dict]:
    frame = frame.fillna("").copy()
    frame["symbol"] = frame["symbol"].str.replace(".", "-", regex=False)
    frame = frame[(frame["created_at"] < "2016-01-01") & (frame["date_added"].str[:10] < "2016-01-01")]
    safe, blocked = {}, {}
    for symbol in sorted(targets):
        candidates = set(frame.loc[frame["symbol"] == symbol, "cik"]) - {""}
        if len(candidates) != 1:
            blocked[symbol] = "missing_historical_cik" if not candidates else "ambiguous_historical_cik"
            continue
        cik = next(iter(candidates)).zfill(10)
        if any(mapping.get(symbol) and mapping[symbol] != cik for mapping in (live, stored)):
            blocked[symbol] = "issuer_conflict_or_reused_ticker"
        else:
            safe[symbol] = cik
    return safe, blocked
