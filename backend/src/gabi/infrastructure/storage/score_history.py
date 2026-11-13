"""Daily score of every company (#328). Only the daily task writes; readers never create the table."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS score_history (
 day TEXT NOT NULL, model_id TEXT NOT NULL, metrics_version TEXT, symbol TEXT NOT NULL,
 score REAL NOT NULL, rank INTEGER NOT NULL, universe INTEGER NOT NULL, recorded_at TEXT NOT NULL,
 PRIMARY KEY (day, model_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_score_history_symbol ON score_history(symbol, day);
"""
MAX_DAYS = 2000  # About 8 years of sessions for one company.


class SqliteScoreHistory:
    def __init__(self, data_dir: Path, now=lambda: datetime.now(UTC)):
        self.path, self.now = data_dir / "gabi.db", now

    def record(self, day: str, model_id: str, metrics_version: str | None, rows: list[tuple[str, float, int]],
               universe: int) -> int:
        """Replaces the day's rows of that model (a rerun the same day keeps the last one)."""
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM score_history WHERE day=? AND model_id=?", (day, model_id))
            stamp = self.now().isoformat(timespec="seconds")
            db.executemany("INSERT INTO score_history VALUES(?,?,?,?,?,?,?,?)",
                           [(day, model_id, metrics_version, symbol, score, rank, universe, stamp)
                            for symbol, score, rank in rows])
            db.commit()
        return len(rows)

    def _read(self) -> sqlite3.Connection | None:
        if not self.path.is_file():
            return None
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.execute("PRAGMA query_only=ON")
        if db.execute("SELECT 1 FROM sqlite_schema WHERE name='score_history'").fetchone() is None:
            db.close()
            return None
        return db

    def company(self, symbol: str) -> list[dict]:
        """Its recorded days, oldest first."""
        db = self._read()
        if db is None:
            return []
        with closing(db):
            rows = db.execute("SELECT day,model_id,score,rank,universe FROM score_history WHERE symbol=? "
                              "ORDER BY day DESC, model_id DESC LIMIT ?", (symbol, MAX_DAYS)).fetchall()
        return [{"day": day, "model_id": model, "score": score, "rank": rank, "universe": universe}
                for day, model, score, rank, universe in reversed(rows)]

    def recorded_days(self, since: str) -> list[str]:
        """Days from `since` on with a stored score of any model, oldest first."""
        db = self._read()
        if db is None:
            return []
        with closing(db):
            rows = db.execute("SELECT DISTINCT day FROM score_history WHERE day>=? ORDER BY day", (since,)).fetchall()
        return [day for (day,) in rows]

    def previous_day(self, model_id: str, before: str) -> tuple[str, dict[str, tuple[float, int]]] | None:
        """The latest recorded day of `model_id` strictly before `before`, with every company's score and rank."""
        db = self._read()
        if db is None:
            return None
        with closing(db):
            found = db.execute("SELECT MAX(day) FROM score_history WHERE model_id=? AND day<?",
                               (model_id, before)).fetchone()[0]
            if found is None:
                return None
            rows = db.execute("SELECT symbol,score,rank FROM score_history WHERE model_id=? AND day=?",
                              (model_id, found)).fetchall()
        return found, {symbol: (score, rank) for symbol, score, rank in rows}
