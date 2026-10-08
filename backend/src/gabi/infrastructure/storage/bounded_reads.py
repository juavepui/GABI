"""SQLite read primitives shared by bounded local query adapters."""

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path


@contextmanager
def read_only(path: Path, max_field_bytes: int):
    if not path.is_file():
        yield None, set()
        return
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, max(65536, max_field_bytes * 4))
        tables = {name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        yield db, tables


def bounded_rows(db, query, params, *, max_rows: int, max_bytes: int, max_field_bytes: int) -> list[tuple]:
    return list(bounded_records(db, query, params, max_rows=max_rows, max_bytes=max_bytes,
                                max_field_bytes=max_field_bytes))


def bounded_records(db, query, params, *, max_rows: int, max_bytes: int, max_field_bytes: int):
    """Stream a bounded query so consumers can discard intermediate rows."""
    count = 0
    size = 0
    try:
        for row in db.execute(query + " LIMIT ?", (*params, max_rows + 1)):
            lengths = [len(value.encode()) if isinstance(value, str) else 8 for value in row]
            size += sum(lengths)
            if count >= max_rows or size > max_bytes or any(n > max_field_bytes for n in lengths):
                raise ValueError("La consulta supera el límite de lectura.")
            count += 1
            yield row
    except sqlite3.DataError as exc:
        if exc.sqlite_errorcode != sqlite3.SQLITE_TOOBIG:
            raise
        raise ValueError("El registro supera el límite de SQLite.") from exc
