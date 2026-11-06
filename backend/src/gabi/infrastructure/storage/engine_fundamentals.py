"""``engine_fundamentals`` in gabi.db (#347): the tested engine's eight company metrics of one day.

Written only by an explicit action (the daily task or ``gabi_cli periodic --motor``); a query never creates the
table. Each write replaces every row in one transaction, so a company that left the universe or that the engine
could not compute does not keep yesterday's value. The ranking-input revision triggers of #342 cover the table.
"""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from gabi.domain.market.engine_fundamentals import METRICS

SCHEMA = ("CREATE TABLE IF NOT EXISTS engine_fundamentals (symbol TEXT PRIMARY KEY, as_of TEXT NOT NULL, "
          "rule_version TEXT NOT NULL, computed_at TEXT NOT NULL, "
          + ", ".join(f"{metric} REAL" for metric in METRICS) + ")")


class SqliteEngineFundamentals:
    def __init__(self, path: Path):
        self.path = path

    def replace(self, rows: list[dict], computed_at: datetime) -> int:
        if not self.path.is_file():
            raise FileNotFoundError("Sin base de datos local: no se crea desde aquí.")
        columns = ("symbol", "as_of", "rule_version", "computed_at", *METRICS)
        stamp = computed_at.isoformat()
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(SCHEMA)
                db.execute("DELETE FROM engine_fundamentals")
                db.executemany(f"INSERT INTO engine_fundamentals ({','.join(columns)}) "
                               f"VALUES ({','.join('?' * len(columns))})",
                               [(row["symbol"], row["as_of"], row["rule_version"], stamp,
                                 *(row[metric] for metric in METRICS)) for row in rows])
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return len(rows)
