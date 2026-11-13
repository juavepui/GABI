"""Append-only revisions in gabi.db: the investor profile (#244) and the portfolio policy (#248).

GET never initializes the table; every save adds a revision and leaves the earlier ones as they were."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
 revision INTEGER PRIMARY KEY AUTOINCREMENT, version TEXT NOT NULL, profile TEXT NOT NULL, created_at TEXT NOT NULL
);
"""
TABLES = ("investor_profiles", "portfolio_policies")
MAX_REVISIONS = 50


class SqliteInvestorProfile:
    def __init__(self, data_dir: Path, table: str = "investor_profiles"):
        if table not in TABLES:
            raise ValueError(f"Unknown revisions table: {table}")
        self.path, self.table = data_dir / "gabi.db", table

    def _read(self) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (self.table,)).fetchone() is None:
            db.close()
            return None
        return db

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        return {"revision": row["revision"], "version": row["version"], "created_at": row["created_at"],
                "profile": json.loads(row["profile"])}

    def latest(self) -> dict | None:
        db = self._read()
        if db is None:
            return None
        with closing(db):
            row = db.execute(f"SELECT * FROM {self.table} ORDER BY revision DESC LIMIT 1").fetchone()
        return None if row is None else self._row(row)

    def revisions(self) -> list[dict]:
        db = self._read()
        if db is None:
            return []
        with closing(db):
            rows = db.execute(f"SELECT * FROM {self.table} ORDER BY revision DESC LIMIT ?",
                              (MAX_REVISIONS,)).fetchall()
        return [self._row(row) for row in rows]

    def save(self, version: str, profile: dict, now: str) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.executescript(SCHEMA.format(table=self.table))
            cursor = db.execute(f"INSERT INTO {self.table}(version,profile,created_at) VALUES (?,?,?)",
                                (version, json.dumps(profile, sort_keys=True), now))
            return int(cursor.lastrowid or 0)
