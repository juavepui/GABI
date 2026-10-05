"""Offline, additive identity migration over the old identity store (`gabi_cli research entity-migration`).

No legacy rows are deleted or automatically attributed using today's ticker map.
The database is the configured one (``GABI_DATA_DIR``); this bridge never redirects
the global configuration to another file.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd

from gabi import identity, storage
from gabi.domain.research import identity_coverage
from gabi.historical_ticker_corrections import WLP_END, WLP_SOURCES, WLP_START

# Bounds are trading dates, not corporate-name effective dates. Multiple
# independent sources are retained; open ends express continuity until new evidence.
KNOWN_ALIASES = [
    ("1156039", "WellPoint Inc.", "WLP", WLP_START, "2010-02-16", WLP_SOURCES[0]),
    ("1156039", "WellPoint Inc.", "WLP", "2010-02-16", WLP_END,
     "https://www.sec.gov/Archives/edgar/data/1156039/000119312510031423/dex991.htm | "
     "https://www.miaxglobal.com/alert/2014/12/02/miax-corporate-action-alert-wellpoint-inc-wlp-name-and-symbol-change-anthem"),
    ("1326801", "Meta Platforms", "FB", "2012-05-18", "2022-06-09",
     "https://www.sec.gov/Archives/edgar/data/1326801/000132680114000007/fb-12312013x10k.htm"),
    ("1326801", "Meta Platforms", "META", "2022-06-09", None,
     "https://www.sec.gov/Archives/edgar/data/1326801/000132680123000052/meta-12312022x10kars.htm"),
    ("1156039", "Elevance Health", "ANTM", "2014-12-03", "2022-06-28",
     "https://www.miaxglobal.com/alert/2014/12/02/miax-corporate-action-alert-wellpoint-inc-wlp-name-and-symbol-change-anthem"),
    ("1156039", "Elevance Health", "ELV", "2022-06-28", None,
     "https://www.sec.gov/Archives/edgar/data/1156039/000115603922000081/elv-20220630.htm"),
]


def backup_once(db: Path) -> None:
    """Copy the database once before the first identity write."""
    if not db.exists():
        return
    backup = db.with_name(db.name + ".before-identity.bak")
    if not backup.exists():
        with sqlite3.connect(db) as original, sqlite3.connect(backup) as destination:
            original.backup(destination)


def activate_reviewed_symbol(symbol: str) -> int:
    """Activate one reviewed ticker interval without migrating unrelated symbols."""
    selected = [row for row in KNOWN_ALIASES if identity.normalize_symbol(row[2]) == identity.normalize_symbol(symbol)]
    if not selected:
        raise ValueError(f"No reviewed alias for {symbol}")
    for cik, _name, ticker, start, end, source in selected:
        # Historical labels must not overwrite the issuer's current display name.
        entity = identity.ensure_entity(cik)
        identity.add_alias(entity, ticker, start, end, source=source)
    return len(selected)


def activate(symbol: str) -> dict:
    return {"activated": activate_reviewed_symbol(symbol), "symbol": identity.normalize_symbol(symbol)}


def migrate() -> dict:
    """Idempotent DDL + reviewed aliases + dated legacy snapshots, no network."""
    with storage.get_connection() as conn:
        identity.ensure_schema(conn)
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='entity_snapshots'").fetchone()
        rows = conn.execute("SELECT symbol,cik,name,sector,industry,effective_date FROM entity_snapshots").fetchall() if exists else []
        conn.commit()
    imported = 0
    for symbol, cik, name, sector, industry, day in rows:
        if not cik:
            continue
        entity = identity.import_filing_identity(symbol, cik, day, source="legacy-snapshot:observed-date", name=name)
        with storage.get_connection() as conn:
            identity.put_observations(conn, entity, "sector", symbol, [{
                "cik": cik, "name": name, "sector": sector, "industry": industry, "effective_date": day,
            }], "legacy-snapshot:observed-date")
            conn.commit()
        imported += 1
    for symbol in sorted({row[2] for row in KNOWN_ALIASES}):
        activate_reviewed_symbol(symbol)
    return {"snapshots_imported": imported, "reviewed_aliases": len(KNOWN_ALIASES),
            "legacy_financial_rows_attributed": 0}


def attribute_legacy(symbol: str, entity_id: str, dataset: str, *, source: str,
                     start: str | None = None, end: str | None = None) -> int:
    """Explicit operator attestation of ownership, after inspecting provider evidence.

    This is deliberately not inferred from the latest edgar_metrics.cik: old
    rows for the symbol could have been fetched for a different issuer.
    """
    identity_coverage.check_attribution(dataset, source, start, end)
    with storage.get_connection() as conn:
        identity.ensure_schema(conn)
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (dataset,)).fetchone()
        if not exists:
            return 0
        frame = pd.read_sql_query(f'SELECT * FROM "{dataset}" WHERE symbol=?', conn, params=(symbol,))
        rows = identity_coverage.attribution_rows(frame, dataset, start, end)
        identity.put_observations(conn, entity_id, dataset, symbol, rows, source)
        conn.commit()
    return len(rows)


def import_candidates(symbol: str, historical_name: str, submissions: Path, source: str):
    return identity.import_submissions_candidates(symbol, historical_name,
                                                  json.loads(submissions.read_text(encoding="utf-8")), source=source)


def coverage_report(history: pd.DataFrame, current_map: pd.DataFrame) -> dict:
    # Read alias evidence once: the historical file can contain millions of pairs.
    with storage.get_connection() as conn:
        identity.ensure_schema(conn)
        aliases = pd.read_sql_query("SELECT * FROM entity_aliases", conn)
    return identity_coverage.coverage(history, current_map, aliases, identity.normalize_symbol, identity.MIN_CONFIDENCE)


def write_report(history_path: Path, cik_map_path: Path, destination: Path) -> dict:
    report = coverage_report(pd.read_csv(history_path, keep_default_na=False),
                             pd.read_csv(cik_map_path, dtype={"cik": str}, keep_default_na=False))
    report["history_sha256"] = hashlib.sha256(history_path.read_bytes()).hexdigest()
    report["cik_map_sha256"] = hashlib.sha256(cik_map_path.read_bytes()).hexdigest()
    history = pd.read_csv(history_path, keep_default_na=False)
    recent = history[history["date"] >= "2016-01-01"]
    if not recent.empty:
        report["since_2016"] = coverage_report(recent, pd.read_csv(cik_map_path, keep_default_na=False))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
