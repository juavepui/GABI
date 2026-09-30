"""Bounded, explicit access to cached decision prices and legacy saved plans."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from gabi.application.errors import QueryError


class SqliteDecisions:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def _read(self, table: str) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (table,)).fetchone() is None:
            db.close()
            return None
        return db

    def histories(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        if len(symbols) > 1000 or len(set(symbols)) != len(symbols):
            raise QueryError("resource_limit", "El universo de decisiones supera 1000 empresas.", 422)
        db = self._read("prices")
        if db is None:
            return {}
        with closing(db):
            columns = {row[1] for row in db.execute("PRAGMA table_info(prices)")}
            if "adj_close" not in columns:
                return {}
            result = {}
            for offset in range(0, len(symbols), 25):
                batch = symbols[offset:offset + 25]
                marks = ",".join("?" for _ in batch)
                rows = db.execute("SELECT symbol,date,adj_close FROM ("
                                  "SELECT symbol,date,adj_close,ROW_NUMBER() OVER ("
                                  "PARTITION BY symbol ORDER BY date DESC) AS rn FROM prices "
                                  f"WHERE symbol IN ({marks})) WHERE rn<=756 ORDER BY symbol,date", batch).fetchall()
                frame = pd.DataFrame([dict(row) for row in rows])
                if frame.empty:
                    continue
                frame["date"] = pd.to_datetime(frame["date"])
                for symbol, group in frame.groupby("symbol", sort=False):
                    result[str(symbol)] = group.drop(columns="symbol").set_index("date")
            return result

    def progress_histories(self, symbols: list[str], start: str) -> dict[str, pd.DataFrame]:
        if len(symbols) > 31 or len(set(symbols)) != len(symbols):
            raise QueryError("resource_limit", "El plan supera el limite de 30 posiciones.", 422)
        db = self._read("prices")
        if db is None:
            return {}
        with closing(db):
            if "adj_close" not in {row[1] for row in db.execute("PRAGMA table_info(prices)")}:
                return {}
            result = {}
            for symbol in symbols:
                rows = db.execute("SELECT date,adj_close FROM prices WHERE symbol=? AND date>=? "
                                  "ORDER BY date LIMIT 5001", (symbol, start)).fetchall()
                if len(rows) > 5000:
                    raise QueryError("resource_limit", "El progreso supera 5000 sesiones por empresa.", 422)
                if rows:
                    frame = pd.DataFrame([dict(row) for row in rows])
                    frame["date"] = pd.to_datetime(frame["date"])
                    result[symbol] = frame.set_index("date")
            return result

    def list(self) -> list[dict]:
        db = self._read("decision_runs")
        if db is None:
            return []
        with closing(db):
            columns = {row[1] for row in db.execute("PRAGMA table_info(decision_runs)")}
            name = "COALESCE(NULLIF(TRIM(name),''), 'Plan #' || id) AS name" if "name" in columns \
                else "'Plan #' || id AS name"
            return [dict(row) for row in db.execute(
                f"SELECT id,{name},created_at,method FROM decision_runs ORDER BY id DESC LIMIT 100")]

    def get(self, plan_id: int) -> dict | None:
        db = self._read("decision_runs")
        if db is None:
            return None
        with closing(db):
            columns = {row[1] for row in db.execute("PRAGMA table_info(decision_runs)")}
            name = "COALESCE(NULLIF(TRIM(name),''), 'Plan #' || id) AS name" if "name" in columns \
                else "'Plan #' || id AS name"
            row = db.execute(f"SELECT id,{name},created_at,method,decisions_json,policy_json,holdings_json "
                             "FROM decision_runs WHERE id=?", (plan_id,)).fetchone()
            if row is None:
                return None
            record = dict(row)
            for key in ("decisions", "policy", "holdings"):
                record[key] = json.loads(record.pop(key + "_json"))
            return record

    def save(self, result: dict, name: str, job_id: str) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS decision_runs (id INTEGER PRIMARY KEY, "
                       "created_at TEXT NOT NULL, method TEXT NOT NULL, decisions_json TEXT NOT NULL, "
                       "policy_json TEXT NOT NULL, holdings_json TEXT NOT NULL, name TEXT)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(decision_runs)")}
            if "name" not in columns:
                db.execute("ALTER TABLE decision_runs ADD COLUMN name TEXT")
            if "source_job_id" not in columns:
                db.execute("ALTER TABLE decision_runs ADD COLUMN source_job_id TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_decision_runs_source_job ON "
                       "decision_runs(source_job_id)")
            existing = db.execute("SELECT id FROM decision_runs WHERE source_job_id=?", (job_id,)).fetchone()
            if existing:
                return int(existing[0])
            cursor = db.execute("INSERT INTO decision_runs "
                                "(created_at,method,decisions_json,policy_json,holdings_json,name,source_job_id) "
                                "VALUES(?,?,?,?,?,?,?)", (datetime.now(UTC).isoformat(), result["method"],
                                json.dumps(result["decisions"], ensure_ascii=False, allow_nan=False),
                                json.dumps(result["policy"], allow_nan=False),
                                json.dumps(result["holdings"], allow_nan=False), name, job_id))
            db.commit()
            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

    def rename(self, plan_id: int, name: str) -> bool:
        if not self.path.is_file():
            return False
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            cursor = db.execute("UPDATE decision_runs SET name=? WHERE id=?", (name, plan_id))
            db.commit()
            return cursor.rowcount == 1

    def delete(self, plan_id: int) -> bool:
        if not self.path.is_file():
            return False
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            cursor = db.execute("DELETE FROM decision_runs WHERE id=?", (plan_id,))
            db.commit()
            return cursor.rowcount == 1
