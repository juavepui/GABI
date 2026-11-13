"""Reported EPS writes and bounded nearest-price reads, with explicit directory and clock."""
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from gabi.domain.market.events import EARNINGS_HISTORY_SOURCE
from gabi.infrastructure.storage.company_research import SqliteCompanyResearch

SCHEMA = """
CREATE TABLE IF NOT EXISTS earnings_surprises (
 symbol TEXT NOT NULL, earnings_date TEXT NOT NULL, eps_estimate REAL, eps_reported REAL,
 surprise_pct REAL, price_reaction_pct REAL, source TEXT NOT NULL, recorded_at TEXT NOT NULL,
 PRIMARY KEY (symbol, earnings_date)
);
"""


class SqliteEarnings:
    def __init__(self, data_dir: Path, *, now: Callable[[], datetime] | None = None):
        self.path = data_dir / "gabi.db"
        self.reader = SqliteCompanyResearch(data_dir)
        self.now = now or (lambda: datetime.now(UTC))

    def save(self, rows: list[dict]) -> None:
        if not rows:
            return
        recorded_at = self.now().isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.executescript(SCHEMA)
            db.executemany(
                "INSERT OR REPLACE INTO earnings_surprises "
                "(symbol,earnings_date,eps_estimate,eps_reported,surprise_pct,price_reaction_pct,source,recorded_at) "
                "VALUES (?,?,?,?,?,?,?,?)", [
                    (row["symbol"], row["earnings_date"].isoformat(), row.get("eps_estimate"), row["eps_reported"],
                     row.get("surprise_pct"), row.get("price_reaction_pct"), EARNINGS_HISTORY_SOURCE, recorded_at)
                    for row in rows])
            db.commit()

    def read(self, symbol: str) -> pd.DataFrame:
        return self.reader.surprises(symbol)

    def reaction_prices(self, symbol: str, dates: list[date]) -> pd.DataFrame:
        if not dates or not self.path.is_file():
            return pd.DataFrame()
        if len(dates) > 200:
            raise ValueError("El histórico de sorpresas supera 200 fechas.")
        targets = list(dict.fromkeys(day.isoformat() for day in dates))
        marks = ",".join("(?)" for _ in targets)
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=30)) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name='prices'").fetchone() is None:
                return pd.DataFrame()
            pairs = db.execute(
                f"WITH targets(day) AS (VALUES {marks}) SELECT "
                "(SELECT date FROM prices WHERE symbol=? AND date<day ORDER BY date DESC LIMIT 1),"
                "(SELECT adj_close FROM prices WHERE symbol=? AND date<day ORDER BY date DESC LIMIT 1),"
                "(SELECT date FROM prices WHERE symbol=? AND date>=day ORDER BY date ASC LIMIT 1),"
                "(SELECT adj_close FROM prices WHERE symbol=? AND date>=day ORDER BY date ASC LIMIT 1) "
                "FROM targets", (*targets, symbol, symbol, symbol, symbol)).fetchall()
        values = {day: value for row in pairs for day, value in ((row[0], row[1]), (row[2], row[3]))
                  if day is not None}
        return pd.DataFrame({"adj_close": list(values.values())}, index=pd.to_datetime(list(values))).sort_index()
