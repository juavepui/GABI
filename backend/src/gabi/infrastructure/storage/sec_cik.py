"""Bounded SEC map files and operation-scoped resolution persistence."""

import io
import os
import sqlite3
import tempfile
from collections.abc import Callable
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS cik_resolutions (
    symbol TEXT PRIMARY KEY, cik TEXT NOT NULL, title TEXT, resolved_at TEXT NOT NULL
);
"""


class FileCikMap:
    def __init__(self, path: Path, *, max_bytes: int = 16 * 1024 * 1024, max_rows: int = 50000):
        self.path, self.max_bytes, self.max_rows = path, max_bytes, max_rows

    def exists(self) -> bool:
        return self.path.is_file()

    def modified_at(self) -> float:
        return self.path.stat().st_mtime

    def read(self) -> pd.DataFrame:
        with self.path.open("rb") as file:
            size = os.fstat(file.fileno()).st_size
            if size > self.max_bytes:
                raise ValueError("El mapa CIK supera el límite de bytes.")
            raw = file.read(size + 1)
        if len(raw) > self.max_bytes:
            raise ValueError("El mapa CIK supera el límite de bytes.")
        if len(raw) != size:
            raise ValueError("El mapa CIK cambió durante la lectura.")
        frame = pd.read_csv(io.BytesIO(raw), dtype={"cik": str}, nrows=self.max_rows + 1)
        if len(frame) > self.max_rows:
            raise ValueError("El mapa CIK supera el límite de filas.")
        return frame

    def save(self, frame: pd.DataFrame) -> None:
        if len(frame) > self.max_rows:
            raise ValueError("El mapa CIK supera el límite de filas.")
        raw = frame.to_csv(index=False).encode()
        if len(raw) > self.max_bytes:
            raise ValueError("El mapa CIK supera el límite de bytes.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".sec_cik_", suffix=".tmp", dir=self.path.parent)
        pending = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(raw)
            pending.replace(self.path)
        finally:
            pending.unlink(missing_ok=True)


class SqliteCikResolutions:
    def __init__(self, path: Path, clock: Callable[[], datetime], *, max_field_bytes: int = 16384):
        self.path, self.clock, self.max_field_bytes = path, clock, max_field_bytes

    def remember(self, symbol: str, cik: str, title: str) -> None:
        if any(len(str(value).encode()) > self.max_field_bytes for value in (symbol, cik, title)):
            raise ValueError("La resolución CIK supera el límite de campo.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.executescript(SCHEMA)
            with db:
                db.execute("INSERT OR REPLACE INTO cik_resolutions VALUES (?,?,?,?)",
                           (symbol, cik, title, self.clock().isoformat()))

    def remember_many(self, values: dict[str, tuple]) -> None:
        if len(values) > 1000 or any(len(str(value).encode()) > self.max_field_bytes
                                    for symbol, pair in values.items() for value in (symbol, *pair)):
            raise ValueError("Las resoluciones CIK superan el límite de escritura.")
        if not values:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            db.executescript(SCHEMA)
            with db:
                db.executemany("INSERT OR REPLACE INTO cik_resolutions VALUES (?,?,?,?)",
                               [(symbol, cik, title, self.clock().isoformat()) for symbol, (cik, title) in values.items()])

    def cached_many(self, symbols: list[str]) -> dict[str, tuple]:
        symbols = list(dict.fromkeys(symbols))
        if len(symbols) > 1000:
            raise ValueError("Las resoluciones CIK superan el límite de símbolos.")
        result = {symbol: (None, None) for symbol in symbols}
        if not symbols or not self.path.is_file():
            return result
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            for start in range(0, len(symbols), 200):
                chunk = symbols[start:start + 200]
                marks = ",".join("?" for _ in chunk)
                try:
                    rows = db.execute("SELECT symbol,CASE WHEN length(CAST(cik AS BLOB))<=? THEN cik END, "
                                      "CASE WHEN COALESCE(length(CAST(title AS BLOB)),0)<=? THEN title END, "
                                      "length(CAST(cik AS BLOB)), COALESCE(length(CAST(title AS BLOB)),0) "
                                      f"FROM cik_resolutions WHERE symbol IN ({marks})",
                                      (self.max_field_bytes, self.max_field_bytes, *chunk)).fetchall()
                except sqlite3.OperationalError as exc:
                    if str(exc) != "no such table: cik_resolutions":
                        raise
                    return result
                for symbol, cik, title, cik_size, title_size in rows:
                    if max(cik_size, title_size) > self.max_field_bytes:
                        raise ValueError("La resolución CIK supera el límite de campo.")
                    result[symbol] = (cik, title)
        return result

    def cached(self, symbol: str) -> tuple:
        if not self.path.is_file():
            return None, None
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            try:
                row = db.execute("SELECT CASE WHEN length(CAST(cik AS BLOB))<=? AND "
                                 "COALESCE(length(CAST(title AS BLOB)),0)<=? THEN cik END, "
                                 "CASE WHEN COALESCE(length(CAST(title AS BLOB)),0)<=? THEN title END, "
                                 "length(CAST(cik AS BLOB)), COALESCE(length(CAST(title AS BLOB)),0) "
                                 "FROM cik_resolutions WHERE symbol=?",
                                 (self.max_field_bytes, self.max_field_bytes, self.max_field_bytes, symbol)).fetchone()
            except sqlite3.OperationalError as exc:
                if str(exc) != "no such table: cik_resolutions":
                    raise
                return None, None
        if row and max(row[2:]) > self.max_field_bytes:
            raise ValueError("La resolución CIK supera el límite de campo.")
        return (row[0], row[1]) if row else (None, None)
