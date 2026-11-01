"""Separate SQLite store of the CBOP-v1 data gate (#252): issuer facts by CIK, outside the operational tables.

The gate needs the issuers that left the S&P 500 as well as the current ones; the
operational sync is keyed by today's tickers and must not receive delisted or
recycled symbols. This store holds only the CbOP tags of each downloaded CIK, the
SIC its submissions declared and the hash of each payload.
"""

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cbop_downloads (
 cik TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
 sic INTEGER, facts_sha256 TEXT, submissions_sha256 TEXT, rows INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cbop_facts (
 cik TEXT NOT NULL, tag TEXT NOT NULL, unit TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
 val REAL NOT NULL, form TEXT, fp TEXT, fy INTEGER, filed_date TEXT, accn TEXT NOT NULL,
 PRIMARY KEY(cik,tag,unit,start_date,end_date,accn)
);
"""
COLUMNS = ("tag", "unit", "start_date", "end_date", "val", "form", "fp", "fy", "filed_date", "accn")


class SqliteCbopFacts:
    def __init__(self, path: Path):
        self.path = path

    def _write(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        for statement in SCHEMA.strip().split(";"):
            if statement.strip():
                db.execute(statement)
        return db

    def _read(self) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        db.execute("PRAGMA query_only=ON")
        return db

    def downloaded(self) -> dict[str, str]:
        """CIK → status of every finished download (``ok`` or ``absent``)."""
        db = self._read()
        if db is None:
            return {}
        with closing(db):
            return dict(db.execute("SELECT cik,status FROM cbop_downloads"))

    def save(self, cik: str, *, rows: Iterable[dict], sic: int | None, status: str, reason: str | None,
             fetched_at: str, facts_sha256: str | None, submissions_sha256: str | None) -> None:
        records = [(cik, *(row[column] for column in COLUMNS)) for row in rows]
        with closing(self._write()) as db, db:
            db.execute("DELETE FROM cbop_facts WHERE cik=?", (cik,))
            db.executemany(f"INSERT OR REPLACE INTO cbop_facts VALUES ({','.join('?' * (len(COLUMNS) + 1))})",
                           records)
            db.execute("INSERT OR REPLACE INTO cbop_downloads VALUES (?,?,?,?,?,?,?,?)",
                       (cik, fetched_at, status, reason, sic, facts_sha256, submissions_sha256, len(records)))

    def downloaded_summary(self) -> dict:
        """Counts and payload hashes of the downloads: the provenance of an audit."""
        db = self._read()
        if db is None:
            return {"issuers": 0}
        with closing(db):
            rows = db.execute("SELECT cik,status,fetched_at,facts_sha256,submissions_sha256,rows FROM cbop_downloads "
                              "ORDER BY cik").fetchall()
        digest = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
        return {"issuers": len(rows), "ok": sum(row[1] == "ok" for row in rows),
                "absent": sum(row[1] == "absent" for row in rows), "first_fetch": min((row[2] for row in rows), default=None),
                "last_fetch": max((row[2] for row in rows), default=None), "manifest_sha256": digest}

    def sic(self, cik: str) -> int | None:
        db = self._read()
        if db is None:
            return None
        with closing(db):
            row = db.execute("SELECT sic FROM cbop_downloads WHERE cik=?", (cik,)).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def facts(self, cik: str) -> dict:
        """The stored facts of one CIK in ``companyfacts`` shape (``us-gaap`` family)."""
        db = self._read()
        families: dict = {}
        if db is None:
            return {"facts": {"us-gaap": families}}
        with closing(db):
            rows = db.execute(f"SELECT {','.join(COLUMNS)} FROM cbop_facts WHERE cik=? ORDER BY end_date,filed_date",
                              (cik,)).fetchall()
        for tag, unit, start, end, val, form, fp, fy, filed, accn in rows:
            families.setdefault(tag, {"units": {}})["units"].setdefault(unit, []).append(
                {"start": start or None, "end": end, "val": val, "form": form, "fp": fp, "fy": fy, "filed": filed,
                 "accn": accn})
        return {"facts": {"us-gaap": families}}


def identity_intervals(database: Path) -> list[dict]:
    """The accredited historical identity intervals (2010–2015 and 2016–2025) of ``gabi.db``, read only."""
    if not database.is_file():
        return []
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute("SELECT symbol,cik,valid_from,valid_to,status FROM historical_identity_intervals").fetchall()
    return [{"symbol": symbol, "cik": cik, "valid_from": start, "valid_to": end, "status": status}
            for symbol, cik, start, end, status in rows]
