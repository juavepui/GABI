"""Stored 8-K rows of the SEC submissions index (#292), plus its 10-K/A and NT 10-K rows (#293), by issuer CIK.

Writes come only from explicit downloads (the SEC sync and the per-company job);
reads open the database read-only and never create the table.
"""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from gabi.domain.market import current_reports as rules
from gabi.domain.market import tenk_flags
from gabi.domain.market.identity import normalize_symbol
from gabi.domain.market.sec_xbrl import normalize_cik

SCHEMA = """
CREATE TABLE IF NOT EXISTS sec_current_reports (
    cik TEXT NOT NULL,
    accession TEXT NOT NULL,
    form TEXT NOT NULL,
    filed_date TEXT,
    report_date TEXT,
    items TEXT NOT NULL,
    primary_document TEXT,
    captured_at TEXT NOT NULL,
    PRIMARY KEY (cik, accession)
)
"""
INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS sec_filing_index (
    cik TEXT PRIMARY KEY,
    captured_at TEXT NOT NULL,
    forms TEXT NOT NULL
)
"""
MAX_ROWS = 200
# Forms kept from each index: the 8-Ks and the accounting signs' annual-report forms.
STORED_FORMS = rules.FORMS + tenk_flags.FILING_FORMS


class SqliteCurrentReports:
    def __init__(self, path: Path, now=lambda: datetime.now(UTC)):
        self.path, self.now = path, now

    def save_submissions(self, cik: str, payload: dict) -> int:
        """Adds the stored forms' rows of one submissions payload; a filing already stored is kept as it was.

        It also records which forms that capture looked for, so a missing 10-K/A is known to be absent.
        """
        rows = rules.from_submissions(payload, STORED_FORMS)
        cik = normalize_cik(cik)
        captured = self.now().isoformat()
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute(SCHEMA)
            db.execute(INDEX_SCHEMA)
            before = db.total_changes
            db.executemany(
                "INSERT OR IGNORE INTO sec_current_reports(cik,accession,form,filed_date,report_date,items,"
                "primary_document,captured_at) VALUES (?,?,?,?,?,?,?,?)",
                [(cik, row["accession"], row["form"], row["filed_date"], row["report_date"], row["items"],
                  row["primary_document"], captured) for row in rows])
            added = db.total_changes - before
            db.execute("INSERT OR REPLACE INTO sec_filing_index(cik,captured_at,forms) VALUES (?,?,?)",
                       (cik, captured, ",".join(STORED_FORMS)))
            return added

    def for_symbol(self, symbol: str, limit: int = MAX_ROWS, forms: tuple[str, ...] = rules.FORMS) -> dict:
        """The symbol's stored CIK and its newest rows of ``forms``; empty when nothing was downloaded.

        ``forms`` lists the forms the last capture looked for (``None`` before #293 recorded it).
        """
        empty: dict = {"cik": None, "captured_at": None, "forms": None, "rows": []}
        if not self.path.is_file():
            return empty
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            tables = {name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            if "edgar_metrics" not in tables:
                return empty
            found = db.execute("SELECT cik FROM edgar_metrics WHERE symbol=?", (normalize_symbol(symbol),)).fetchone()
            if not found or not str(found[0] or "").strip().isdigit():
                return empty
            cik = normalize_cik(found[0])
            if "sec_current_reports" not in tables:
                return {**empty, "cik": cik}
            marks = ",".join("?" * len(forms))
            rows = db.execute(
                "SELECT accession,form,filed_date,report_date,items,primary_document,captured_at "
                f"FROM sec_current_reports WHERE cik=? AND form IN ({marks}) "
                "ORDER BY filed_date DESC, accession DESC LIMIT ?",
                (cik, *forms, max(1, min(limit, MAX_ROWS)))).fetchall()
            captured = db.execute("SELECT max(captured_at) FROM sec_current_reports WHERE cik=?", (cik,)).fetchone()[0]
            index = (db.execute("SELECT captured_at,forms FROM sec_filing_index WHERE cik=?", (cik,)).fetchone()
                     if "sec_filing_index" in tables else None)
        keys = ("accession", "form", "filed_date", "report_date", "items", "primary_document")
        return {"cik": cik, "captured_at": index[0] if index else captured,
                "forms": index[1].split(",") if index else None,
                "rows": [dict(zip(keys, row[:6], strict=True)) for row in rows]}
