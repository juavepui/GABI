"""Read only the trading sessions needed for one Factor Lab period."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from gabi.application.research.reservations import require_observed_period

MAX_SYMBOLS = 1_000
MAX_ROWS = 300_000


class SqliteFactorPrices:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def __call__(self, symbols: list[str], first: str, last: str) -> dict:
        require_observed_period(first, last)
        if not symbols:
            return {}
        if len(symbols) > MAX_SYMBOLS or len(set(symbols)) != len(symbols):
            raise ValueError("El universo del Factor Lab supera el límite de lectura.")
        if not self.path.is_file():
            return {}
        result: dict = {}
        remaining = MAX_ROWS
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            for offset in range(0, len(symbols), 200):
                batch = symbols[offset:offset + 200]
                marks = ",".join("?" for _ in batch)
                rows = db.execute(
                    f"SELECT symbol,date,adj_close FROM prices WHERE symbol IN ({marks}) "
                    "AND date>=? AND date<=? ORDER BY symbol,date LIMIT ?",
                    (*batch, first, last, remaining + 1)).fetchall()
                remaining -= len(rows)
                if remaining < 0:
                    raise ValueError("Las series del Factor Lab superan el límite de lectura.")
                frame = pd.DataFrame(rows, columns=["symbol", "date", "adj_close"])
                if frame.empty:
                    continue
                frame["date"] = pd.to_datetime(frame["date"])
                for symbol, group in frame.groupby("symbol"):
                    result[symbol] = group.drop(columns=["symbol"]).set_index("date")
        return result
