"""Persistent issuer identity and attributed observations. All operations are offline.

Aliases use inclusive valid_from and exclusive valid_to. CIK identifies an
issuer, not a security: price series retain their source ticker and never merge
concurrent share classes merely because their CIK matches.
"""
import hashlib
import json
import re
import uuid
from datetime import date

import pandas as pd

from . import storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY, cik TEXT UNIQUE, name TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_aliases (
    entity_id TEXT NOT NULL REFERENCES entities(entity_id), symbol TEXT NOT NULL,
    valid_from TEXT NOT NULL, valid_to TEXT, source TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    PRIMARY KEY(entity_id, symbol, valid_from, source),
    CHECK(valid_to IS NULL OR valid_to > valid_from)
);
CREATE INDEX IF NOT EXISTS idx_entity_alias_symbol ON entity_aliases(symbol, valid_from, valid_to);
CREATE TABLE IF NOT EXISTS entity_observations (
    entity_id TEXT NOT NULL REFERENCES entities(entity_id), dataset TEXT NOT NULL,
    symbol TEXT NOT NULL, record_key TEXT NOT NULL, payload_json TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY(entity_id, dataset, symbol, record_key)
);
CREATE TABLE IF NOT EXISTS entity_candidates (
    symbol TEXT NOT NULL, entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    name TEXT, source TEXT NOT NULL, reason TEXT NOT NULL,
    PRIMARY KEY(symbol, entity_id, source)
);
"""

MIN_CONFIDENCE = 0.9
DATA_KEYS = {
    "prices": ("date",), "splits": ("date",), "fundamentals": ("fetched_at",),
    "edgar_facts": ("tag", "unit", "start_date", "end_date", "accn"),
    "sector": ("effective_date",),
}


def ensure_schema(conn):
    # execute, rather than executescript: do not commit the caller's transaction.
    for statement in SCHEMA.split(";"):
        if statement.strip():
            conn.execute(statement)


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


def normalize_cik(cik) -> str:
    value = str(cik).strip()
    if not value.isdigit() or len(value) > 10 or int(value) == 0:
        raise ValueError("CIK must contain 1-10 digits and be nonzero")
    return value.zfill(10)


def ensure_entity(cik=None, name: str | None = None, *, entity_id: str | None = None) -> str:
    cik = normalize_cik(cik) if cik is not None else None
    name = None if pd.isna(name) else name
    derived = f"cik:{cik}" if cik else entity_id or f"local:{uuid.uuid4()}"
    if cik and entity_id and entity_id != derived:
        raise ValueError("entity_id conflicts with CIK")
    with storage.get_connection() as conn:
        ensure_schema(conn)
        existing = conn.execute("SELECT cik FROM entities WHERE entity_id=?", (derived,)).fetchone()
        if existing and existing[0] != cik:
            raise ValueError("An entity's CIK cannot be reassigned")
        conn.execute("INSERT INTO entities VALUES (?,?,?,?) ON CONFLICT(entity_id) DO UPDATE "
                     "SET name=COALESCE(excluded.name,entities.name)",
                     (derived, cik, name, date.today().isoformat()))
        conn.commit()
    return derived


def add_alias(entity_id: str, symbol: str, valid_from: str, valid_to: str | None = None,
              *, source: str, confidence: float = 1.0):
    """Record dated evidence. Conflicting evidence is retained as ambiguous."""
    start = date.fromisoformat(valid_from).isoformat()
    end = date.fromisoformat(valid_to).isoformat() if valid_to else None
    if not source.strip() or not 0 <= confidence <= 1 or (end and end <= start):
        raise ValueError("Invalid alias evidence, confidence or validity interval")
    symbol = normalize_symbol(symbol)
    if not symbol:
        raise ValueError("Empty symbol")
    with storage.get_connection() as conn:
        ensure_schema(conn)
        if not conn.execute("SELECT 1 FROM entities WHERE entity_id=?", (entity_id,)).fetchone():
            raise ValueError("Unknown entity")
        conn.execute("INSERT INTO entity_aliases VALUES (?,?,?,?,?,?) "
                     "ON CONFLICT(entity_id,symbol,valid_from,source) DO UPDATE SET "
                     "valid_to=excluded.valid_to, confidence=excluded.confidence",
                     (entity_id, symbol, start, end, source, confidence))
        conn.commit()


def resolve(symbol: str, as_of: str) -> dict:
    date.fromisoformat(as_of)
    with storage.get_connection() as conn:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT a.entity_id,e.cik,a.source,a.confidence FROM entity_aliases a "
            "JOIN entities e USING(entity_id) WHERE symbol=? AND valid_from<=? "
            "AND (valid_to IS NULL OR valid_to>?)",
            (normalize_symbol(symbol), as_of, as_of),
        ).fetchall()
    candidates = sorted({r[0] for r in rows})
    # Even a low-confidence contradictory claim must not silently win/lose.
    status = "ambiguous" if len(candidates) > 1 else "unresolved"
    chosen = max(rows, key=lambda r: r[3]) if rows else None
    if len(candidates) == 1 and chosen and chosen[3] >= MIN_CONFIDENCE:
        status = "resolved"
    return {"entity_id": chosen[0] if status == "resolved" and chosen else None,
            "cik": chosen[1] if status == "resolved" and chosen else None,
            "status": status, "candidates": candidates,
            "source": chosen[2] if chosen else None,
            "confidence": chosen[3] if chosen else None}


def has_aliases(symbol: str) -> bool:
    with storage.get_connection() as conn:
        ensure_schema(conn)
        return bool(conn.execute("SELECT 1 FROM entity_aliases WHERE symbol=? LIMIT 1",
                                 (normalize_symbol(symbol),)).fetchone())


def put_observations(conn, entity_id: str, dataset: str, symbol: str, rows: list[dict], source: str):
    """Atomic dual-write used by ingestion; attribution must be explicit."""
    ensure_schema(conn)
    if dataset not in DATA_KEYS or not source:
        raise ValueError("Unknown dataset or missing attribution source")
    if not conn.execute("SELECT 1 FROM entities WHERE entity_id=?", (entity_id,)).fetchone():
        raise ValueError("Unknown entity")
    records = []
    for row in rows:
        row = _json_value(row)
        key = json.dumps([row.get(k, "") for k in DATA_KEYS[dataset]], separators=(",", ":"))
        payload = json.dumps(row, sort_keys=True, default=str, allow_nan=False)
        records.append((entity_id, dataset, normalize_symbol(symbol), key, payload, source))
    if dataset == "edgar_facts":
        # A filing fact is issuer-wide. A refresh under a new alias supersedes
        # the same fact downloaded under the former ticker, not an arbitrary
        # alphabetical duplicate selected at read time.
        conn.executemany("DELETE FROM entity_observations WHERE entity_id=? AND dataset=? AND record_key=?",
                         [(entity_id, dataset, r[3]) for r in records])
    conn.executemany("INSERT OR REPLACE INTO entity_observations VALUES (?,?,?,?,?,?)", records)


def _json_value(value):
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def observations(entity_id: str, dataset: str) -> pd.DataFrame:
    with storage.get_connection() as conn:
        ensure_schema(conn)
        rows = conn.execute("SELECT symbol,payload_json FROM entity_observations "
                            "WHERE entity_id=? AND dataset=? ORDER BY symbol,record_key",
                            (entity_id, dataset)).fetchall()
    return pd.DataFrame([{**json.loads(payload), "source_symbol": symbol} for symbol, payload in rows])


def price_history(symbol: str, as_of: str, *, entity_id: str | None = None) -> pd.DataFrame:
    """Prices attributed to the resolved issuer; never reads the legacy cache.

    Keep a source series intact (split adjustments can differ between downloads).
    Prefer the requested ticker, otherwise allow a single non-concurrent alias.
    Multiple share classes or competing series fail closed.
    """
    resolved = resolve(symbol, as_of)
    owner = entity_id or resolved["entity_id"]
    if not owner or resolved["status"] == "ambiguous" or (resolved["entity_id"] and resolved["entity_id"] != owner):
        return pd.DataFrame()
    frame = observations(owner, "prices")
    if frame.empty:
        return frame
    requested = normalize_symbol(symbol)
    sources = set(frame["source_symbol"])
    if requested in sources:
        frame = frame[frame["source_symbol"] == requested]
    elif len(sources) == 1:
        other = next(iter(sources))
        with storage.get_connection() as conn:
            ensure_schema(conn)
            overlap = conn.execute(
                "SELECT 1 FROM entity_aliases a JOIN entity_aliases b ON a.entity_id=b.entity_id "
                "WHERE a.entity_id=? AND a.symbol=? AND b.symbol=? "
                "AND a.valid_from<COALESCE(b.valid_to,'9999-12-31') "
                "AND b.valid_from<COALESCE(a.valid_to,'9999-12-31') LIMIT 1",
                (owner, requested, other)).fetchone()
        if overlap:
            return pd.DataFrame()
    else:
        return pd.DataFrame()
    # A full history returned for a current ticker can predate that ticker.
    # Its entity attribution is explicit, but observations outside any confirmed
    # alias interval for that issuer must still not extend its known lifetime.
    with storage.get_connection() as conn:
        aliases = conn.execute("SELECT valid_from,valid_to FROM entity_aliases WHERE entity_id=? "
                               "AND confidence>=?", (owner, MIN_CONFIDENCE)).fetchall()
        conflicts = conn.execute(
            "SELECT valid_from,valid_to FROM entity_aliases WHERE symbol=? AND entity_id<>?",
            (requested, owner)).fetchall()
    mask = pd.Series(False, index=frame.index)
    for start, end in aliases:
        mask |= (frame["date"] >= start) & (frame["date"] < (end or "9999-12-31"))
    for start, end in conflicts:
        mask &= ~((frame["date"] >= start) & (frame["date"] < (end or "9999-12-31")))
    frame = frame[mask].copy()
    source_symbol = str(frame["source_symbol"].iloc[0]) if not frame.empty else requested
    frame["date"] = pd.to_datetime(frame["date"])
    result = frame.drop(columns=["source_symbol"]).set_index("date").sort_index()
    result.attrs["source_symbol"] = source_symbol
    return result


def diagnostics(symbols: list[str], as_of: str) -> pd.DataFrame:
    return pd.DataFrame([{"symbol": s, **resolve(s, as_of)} for s in sorted(set(symbols))])


def price_download_symbol(symbol: str, as_of: str, *, today: str | None = None) -> str | None:
    """A live ticker for this historical issuer, only if unambiguous.

    Delisted issuers without a verified successor require an archived series.
    A different company reusing the old symbol is never a download fallback.
    """
    today = today or date.today().isoformat()
    owner = resolve(symbol, as_of)["entity_id"]
    if not owner:
        return None
    if resolve(symbol, today)["entity_id"] == owner:
        return symbol
    with storage.get_connection() as conn:
        aliases = conn.execute("SELECT DISTINCT symbol FROM entity_aliases WHERE entity_id=? "
                               "AND valid_from<=? AND (valid_to IS NULL OR valid_to>?) AND confidence>=?",
                               (owner, today, today, MIN_CONFIDENCE)).fetchall()
    candidates = [r[0] for r in aliases if resolve(r[0], today)["entity_id"] == owner]
    if len(candidates) != 1:
        return None
    with storage.get_connection() as conn:
        overlap = conn.execute(
            "SELECT 1 FROM entity_aliases a JOIN entity_aliases b USING(entity_id) "
            "WHERE a.entity_id=? AND a.symbol=? AND b.symbol=? "
            "AND a.valid_from<COALESCE(b.valid_to,'9999-12-31') "
            "AND b.valid_from<COALESCE(a.valid_to,'9999-12-31') LIMIT 1",
            (owner, normalize_symbol(symbol), candidates[0])).fetchone()
    return None if overlap else candidates[0]


def backtest_prices(symbols: list[str], as_of: str, owners: dict | None = None) -> dict:
    """Entity data for registered issuers; legacy adapter for unmigrated callers.

    Strict ranking excludes unresolved issuers before selection. Other legacy
    callers retain their API; they never bypass a registered/conflicting alias.
    SPY remains the explicitly configured benchmark security, not an issuer.
    """
    from . import config
    result = {}
    for symbol in symbols:
        owner = owners.get(symbol) if owners else None
        if symbol != config.BENCHMARK_SYMBOL and (owner or has_aliases(symbol)):
            result[symbol] = price_history(symbol, as_of, entity_id=owner)
        else:
            result[symbol] = storage.get_prices(symbol)
    return result


def last_filings(symbols: list[str], as_of: str) -> dict:
    from . import edgar
    result = {}
    legacy = []
    for symbol in symbols:
        owner = resolve(symbol, as_of)["entity_id"]
        if owner:
            frame = observations(owner, "edgar_facts")
            if not frame.empty:
                dates = frame.loc[frame["filed_date"].notna() & (frame["filed_date"] <= as_of), "filed_date"]
                if not dates.empty:
                    result[symbol] = dates.max()
        elif not has_aliases(symbol):
            legacy.append(symbol)
    result.update(edgar.get_last_filed_dates(legacy, as_of=as_of))
    return result


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def import_submissions_candidates(symbol: str, historical_name: str, submissions: dict, *, source: str) -> bool:
    """Offline formerNames/name fallback. A match is a candidate, never an alias.

    Dates on formerNames describe names, not ticker trading validity.
    """
    names = [submissions.get("name", ""), *[r.get("name", "") for r in submissions.get("formerNames", [])]]
    if not historical_name or _name_key(historical_name) not in {_name_key(n) for n in names if n}:
        return False
    entity = ensure_entity(submissions["cik"], submissions.get("name"))
    with storage.get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO entity_candidates VALUES (?,?,?,?,?)",
                     (normalize_symbol(symbol), entity, historical_name, source,
                      "Exact normalized name/formerNames match; requires dated ticker evidence"))
        conn.commit()
    return True


def import_filing_identity(symbol: str, cik: str, filing_date: str, *, source: str,
                           name: str | None = None):
    """A filing cover proves a ticker/CIK on its filing date, not an interval."""
    from datetime import timedelta

    entity = ensure_entity(cik, name)
    end = (date.fromisoformat(filing_date) + timedelta(days=1)).isoformat()
    add_alias(entity, symbol, filing_date, end, source=source)
    return entity


def attributed_fingerprint() -> str:
    with storage.get_connection() as conn:
        ensure_schema(conn)
        payload = {table: conn.execute(f"SELECT * FROM {table} ORDER BY 1,2,3").fetchall()
                   for table in ("entities", "entity_aliases", "entity_observations", "entity_candidates")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
