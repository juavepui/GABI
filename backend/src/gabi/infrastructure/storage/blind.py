"""Bounded, read-only blind validation metadata and seal records."""

import sqlite3
from contextlib import closing
from pathlib import Path

from gabi.application.errors import QueryError

MAX_VALIDATIONS = 50
MAX_PERIODS = 100
MAX_TOTAL_PERIODS = 1_000
MAX_JSON_CHARS = 16_384


class SqliteBlindStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def read_status(self) -> list[tuple[dict, list[dict]]]:
        if not self.path.is_file():
            return []
        try:
            db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
            with closing(db):
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only=ON")
                tables = {row[0] for row in db.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table' "
                    "AND name IN ('blind_validations','blind_validation_periods')")}
                if not tables:
                    return []
                if len(tables) != 2:
                    raise QueryError("blind_data_invalid", "El registro ciego está incompleto.", 503)
                validations = db.execute(
                    "SELECT id,name,status,start_date,unlock_date,rebalance_months "
                    "FROM blind_validations ORDER BY id DESC LIMIT ?", (MAX_VALIDATIONS + 1,)).fetchall()
                if len(validations) > MAX_VALIDATIONS:
                    raise QueryError("blind_data_limit", "Hay demasiadas validaciones ciegas para esta consulta.", 503)
                result = []
                total_periods = 0
                for validation in validations:
                    periods = db.execute(
                        "SELECT rebalance_date,substr(symbols_json,1,?) AS symbols_json,"
                        "substr(entry_prices_json,1,?) AS entry_prices_json,prev_hash,record_hash "
                        "FROM blind_validation_periods WHERE validation_id=? ORDER BY rebalance_date LIMIT ?",
                        (MAX_JSON_CHARS + 1, MAX_JSON_CHARS + 1, validation["id"],
                         MAX_PERIODS + 1)).fetchall()
                    total_periods += len(periods)
                    if len(periods) > MAX_PERIODS or total_periods > MAX_TOTAL_PERIODS:
                        raise QueryError("blind_data_limit", "Hay demasiados periodos ciegos para esta consulta.", 503)
                    if any(len(row["symbols_json"]) > MAX_JSON_CHARS or
                           len(row["entry_prices_json"]) > MAX_JSON_CHARS for row in periods):
                        raise QueryError("blind_data_limit", "Un registro ciego supera el límite de lectura.", 503)
                    result.append((dict(validation), [dict(period) for period in periods]))
                return result
        except sqlite3.Error as exc:
            raise QueryError("blind_data_unavailable", "No se puede leer el registro ciego.", 503) from exc
