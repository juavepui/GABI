"""Read old ranking snapshots and signal events without schema changes on GET."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from gabi.application.errors import QueryError

SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS ranking_snapshots (
 id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id INTEGER NOT NULL,
 created_at TEXT NOT NULL, as_of_date TEXT NOT NULL, source TEXT NOT NULL,
 symbol TEXT NOT NULL, rank INTEGER NOT NULL, score REAL NOT NULL, coverage REAL NOT NULL,
 name TEXT, confidence REAL, sector TEXT
);
"""
EVENTS = """
CREATE TABLE IF NOT EXISTS signal_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, detected_at TEXT NOT NULL,
 from_snapshot_id INTEGER, to_snapshot_id INTEGER, symbol TEXT NOT NULL,
 event_type TEXT NOT NULL, severity TEXT NOT NULL, previous_value TEXT,
 new_value TEXT, cause TEXT NOT NULL,
 UNIQUE(from_snapshot_id, to_snapshot_id, symbol, event_type)
);
CREATE INDEX IF NOT EXISTS idx_signal_events_detected ON signal_events(detected_at);
"""


class SqliteSignals:
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

    def snapshots(self) -> list[dict]:
        db = self._read("ranking_snapshots")
        if db is None:
            return []
        with closing(db):
            columns = {row[1] for row in db.execute("PRAGMA table_info(ranking_snapshots)")}
            name = "COALESCE(name, 'Ranking ' || as_of_date)" if "name" in columns else "'Ranking ' || as_of_date"
            rows = db.execute(f"SELECT snapshot_id AS id,{name} AS name,created_at,as_of_date,source,"
                              "COUNT(*) AS candidates FROM ranking_snapshots "
                              "GROUP BY snapshot_id ORDER BY created_at DESC,snapshot_id DESC LIMIT 50").fetchall()
            return [dict(row) for row in rows]

    def snapshot_meta(self, snapshot_id: int) -> dict | None:
        db = self._read("ranking_snapshots")
        if db is None:
            return None
        with closing(db):
            columns = {row[1] for row in db.execute("PRAGMA table_info(ranking_snapshots)")}
            name = "COALESCE(name, 'Ranking ' || as_of_date)" if "name" in columns else "'Ranking ' || as_of_date"
            row = db.execute(f"SELECT snapshot_id AS id,{name} AS name,created_at,as_of_date,source,"
                             "COUNT(*) AS candidates FROM ranking_snapshots WHERE snapshot_id=? GROUP BY snapshot_id",
                             (snapshot_id,)).fetchone()
            return dict(row) if row else None

    def rename(self, snapshot_id: int, name: str) -> bool:
        """The UPDATE of evaluation.rename_snapshot; the name column exists in every saved snapshot table."""
        if not self.path.is_file():
            return False
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name='ranking_snapshots'").fetchone() is None:
                return False
            columns = {row[1] for row in db.execute("PRAGMA table_info(ranking_snapshots)")}
            if "name" not in columns:
                db.execute("ALTER TABLE ranking_snapshots ADD COLUMN name TEXT")
            cursor = db.execute("UPDATE ranking_snapshots SET name=? WHERE snapshot_id=?", (name, snapshot_id))
            db.commit()
            return cursor.rowcount > 0

    def snapshot(self, snapshot_id: int) -> pd.DataFrame:
        db = self._read("ranking_snapshots")
        if db is None:
            return pd.DataFrame()
        with closing(db):
            columns = {row[1] for row in db.execute("PRAGMA table_info(ranking_snapshots)")}
            confidence = "confidence" if "confidence" in columns else "NULL AS confidence"
            sector = "sector" if "sector" in columns else "NULL AS sector"
            rows = db.execute(f"SELECT symbol,rank,score AS composite_score,coverage AS score_coverage,"
                              f"{confidence},{sector} FROM ranking_snapshots WHERE snapshot_id=? ORDER BY rank LIMIT 101",
                              (snapshot_id,)).fetchall()
            if len(rows) > 100:
                raise ValueError("Snapshot superior al límite de 100 candidatas.")
            return pd.DataFrame([dict(row) for row in rows]).set_index("symbol") if rows else pd.DataFrame()

    def filing_facts(self, symbol: str) -> tuple[pd.DataFrame, str | None]:
        db = self._read("edgar_facts")
        if db is None:
            return pd.DataFrame(), None
        with closing(db):
            rows = db.execute("SELECT symbol,tag,unit,start_date,end_date,val,form,fp,fy,filed_date,accn "
                              "FROM edgar_facts WHERE symbol=? AND form IN ('10-K','10-Q') "
                              "ORDER BY end_date,filed_date LIMIT 50001", (symbol,)).fetchall()
            if len(rows) > 50000:
                raise QueryError("resource_limit", "Un historial SEC supera 50000 hechos.", 422)
            cik = None
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name='edgar_metrics'").fetchone():
                row = db.execute("SELECT cik FROM edgar_metrics WHERE symbol=?", (symbol,)).fetchone()
                cik = str(row[0]) if row and row[0] else None
            return pd.DataFrame([dict(row) for row in rows]), cik

    def record_filings(self, snapshot_id: int, results: list[dict]) -> int:
        if not self.path.is_file():
            raise QueryError("data_unavailable", "No hay base local para guardar filings.", 503)
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS filing_metadata (
                    symbol TEXT NOT NULL, form TEXT NOT NULL, accn TEXT NOT NULL,
                    filed_date TEXT NOT NULL, period_end TEXT, url TEXT,
                    PRIMARY KEY (symbol, form, accn));
                CREATE TABLE IF NOT EXISTS filing_comparisons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, form TEXT NOT NULL,
                    current_accn TEXT NOT NULL, previous_accn TEXT NOT NULL, compared_at TEXT NOT NULL,
                    metric TEXT NOT NULL, previous_value REAL, current_value REAL, abs_change REAL,
                    pct_change REAL, severity TEXT NOT NULL, direction TEXT NOT NULL,
                    UNIQUE (symbol, form, current_accn, previous_accn, metric));
            """)
            db.executescript(EVENTS)
            db.execute("BEGIN IMMEDIATE")
            compared_at = datetime.now(UTC).isoformat()
            event_count = 0
            for result in results:
                current, previous = result.get("current"), result.get("previous")
                if not current or not previous:
                    continue
                for filing in (previous, current):
                    db.execute("INSERT OR REPLACE INTO filing_metadata "
                               "(symbol,form,accn,filed_date,period_end,url) VALUES(?,?,?,?,?,?)",
                               (result["symbol"], result["form"], filing["accn"], filing["filed_date"],
                                filing.get("period_end"), filing.get("url")))
                for row in result["rows"]:
                    db.execute("INSERT OR IGNORE INTO filing_comparisons "
                               "(symbol,form,current_accn,previous_accn,compared_at,metric,previous_value,"
                               "current_value,abs_change,pct_change,severity,direction) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                               (result["symbol"], result["form"], current["accn"], previous["accn"],
                                compared_at, row["metric"], row["previous_value"], row["current_value"],
                                row["abs_change"], row["pct_change"], row["severity"], row["direction"]))
                for event in result["events"]:
                    cursor = db.execute("INSERT OR IGNORE INTO signal_events "
                                        "(detected_at,from_snapshot_id,to_snapshot_id,symbol,event_type,severity,"
                                        "previous_value,new_value,cause) VALUES(?,?,?,?,?,?,?,?,?)",
                                        (compared_at, snapshot_id, 0, event["symbol"], event["event_type"],
                                         event["severity"], json.dumps(event["previous_value"]),
                                         json.dumps(event["new_value"]), event["cause"]))
                    event_count += cursor.rowcount
            db.commit()
            return event_count

    def save_snapshot(self, table: pd.DataFrame, as_of_date: str, name: str, top_n: int) -> int:
        candidates = table[table["composite_score"].notna()].head(top_n)
        if candidates.empty:
            raise ValueError("No hay candidatas con score para guardar.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.executescript(SNAPSHOTS)
            columns = {row[1] for row in db.execute("PRAGMA table_info(ranking_snapshots)")}
            for column, definition in (("name", "TEXT"), ("confidence", "REAL"), ("sector", "TEXT")):
                if column not in columns:
                    db.execute(f"ALTER TABLE ranking_snapshots ADD COLUMN {column} {definition}")
            db.execute("BEGIN IMMEDIATE")
            snapshot_id = int(db.execute("SELECT COALESCE(MAX(snapshot_id),0)+1 FROM ranking_snapshots").fetchone()[0])
            created_at = datetime.now(ZoneInfo("Europe/Madrid")).isoformat(timespec="seconds")
            db.executemany("INSERT INTO ranking_snapshots(snapshot_id,created_at,as_of_date,source,symbol,rank,"
                           "score,coverage,name,confidence,sector) VALUES(?,?,?,?,?,?,?,?,?,?,?)", [
                               (snapshot_id, created_at, as_of_date, "react", symbol, rank,
                                float(row["composite_score"]), float(row["score_coverage"]), name,
                                float(row["confidence"]) if pd.notna(row.get("confidence")) else None,
                                str(row["sector"]) if pd.notna(row.get("sector")) else None)
                               for rank, (symbol, row) in enumerate(candidates.iterrows(), 1)
                           ])
            db.commit()
            return snapshot_id

    def events(self, severity: str | None, limit: int, since: str | None = None) -> list[dict]:
        db = self._read("signal_events")
        if db is None:
            return []
        with closing(db):
            conditions, params = [], []
            if severity:
                conditions.append("severity=?")
                params.append(severity)
            if since is not None:  # signal_monitor.list_events(since_hours=...)
                conditions.append("detected_at>=?")
                params.append(since)
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            rows = db.execute("SELECT * FROM signal_events" + where + " ORDER BY detected_at DESC,id DESC LIMIT ?",
                              (*params, limit)).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["previous_value"] = json.loads(item["previous_value"]) if item["previous_value"] else None
                item["new_value"] = json.loads(item["new_value"]) if item["new_value"] else None
                results.append(item)
            return results

    def record(self, events: list[dict], snapshot_id: int) -> None:
        if not events:
            return
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.executescript(EVENTS)
            now = datetime.now(UTC).isoformat()
            db.executemany("INSERT OR IGNORE INTO signal_events(detected_at,from_snapshot_id,to_snapshot_id,"
                           "symbol,event_type,severity,previous_value,new_value,cause) VALUES(?,?,?,?,?,?,?,?,?)", [
                               (now, snapshot_id, 0, event["symbol"], event["event_type"], event["severity"],
                                json.dumps(event["previous_value"]), json.dumps(event["new_value"]), event["cause"])
                               for event in events
                           ])
            db.commit()
