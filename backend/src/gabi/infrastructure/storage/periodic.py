"""Read-only bounded maintenance inputs and explicit log/queue writes."""

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from gabi.domain.research.live_ledger import safe


class PeriodicFiles:
    def __init__(self, data_dir: Path, tiingo_directory: Path, complete: Path, result: Path, deadline: str):
        self.data_dir, self.tiingo_directory = data_dir, tiingo_directory
        self.complete, self.result, self.deadline = complete, result, deadline
        self.queue_path = data_dir / "smallmid_test" / "tiingo_symbols.txt"
        self.lock_path = data_dir / "periodic_tasks" / "tiingo.lock"
        self.log_path = data_dir / "periodic_tasks" / "log.jsonl"

    def live_symbols(self) -> list[str]:
        path = self.data_dir / "sp500_constituents.csv"
        if not path.exists():
            return []
        if path.stat().st_size > 1_000_000:
            raise ValueError("El universo supera el límite de lectura.")
        symbols = pd.read_csv(path, usecols=["symbol"], nrows=1001)["symbol"].tolist()
        if len(symbols) > 1000:
            raise ValueError("El universo supera el límite de lectura.")
        return symbols

    def latest_prices(self, symbols: list[str]) -> dict[str, str | None]:
        path = self.data_dir / "gabi.db"
        result: dict[str, str | None] = dict.fromkeys(symbols)
        if not path.is_file():
            return result
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            if not db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='prices'").fetchone():
                return result
            for start in range(0, len(symbols), 200):
                chunk = symbols[start:start + 200]
                marks = ",".join("?" for _ in chunk)
                result.update(db.execute(f"SELECT symbol,MAX(date) FROM prices WHERE symbol IN ({marks}) "
                                         "AND adj_close IS NOT NULL GROUP BY symbol", chunk).fetchall())
        return result

    def queued_symbols(self) -> list[str]:
        if self.queue_path.stat().st_size > 1_000_000:
            raise ValueError("La cola Tiingo supera el límite de lectura.")
        return [symbol.upper() for symbol in self.queue_path.read_text().split()]

    def tiingo_queue(self) -> dict:
        if not self.queue_path.exists():
            return {"cola": 0, "descargados": 0, "en_curso": False}
        queue = self.queued_symbols()
        done = sum((self.tiingo_directory / f"{symbol}.json").is_file() for symbol in queue)
        return {"cola": len(queue), "descargados": done, "en_curso": self.lock_path.exists()}

    def smallmid_state(self, today: date) -> dict:
        complete = self.complete.exists()
        return {"datos_congelados": complete or today.isoformat() >= self.deadline, "tiingo_completa": complete,
                "fecha_limite": self.deadline, "analizada": self.result.exists()}

    def acquire_tiingo(self, at: datetime) -> str | None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.lock_path.open("x") as stream:
                stream.write(at.isoformat())
        except FileExistsError:
            return f"ya hay una descarga en curso (borrar {self.lock_path} si no es así)"
        return None

    def release_tiingo(self) -> None:
        self.lock_path.unlink(missing_ok=True)

    def log(self, event: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(safe(event), ensure_ascii=False) + "\n")
