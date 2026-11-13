"""Bounded, read-only access to the Research Lab experiment log."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from gabi.application.errors import QueryError

MAX_EXPERIMENTS = 5_000
MAX_TEXT_CHARS = 16_384
MAX_RETURNS_CHARS = 2_000_000

SUMMARY = ("id", "created_at", "model_id", "stage", "family", "n_positions", "rebalance", "sharpe",
           "sortino", "max_drawdown", "hypothesis_registered", "git_commit", "notes", "periods_per_year")
DETAIL = SUMMARY + ("data_cutoff", "universe", "factors", "weights_json", "cost_model", "is_start", "is_end",
                    "oos_start", "oos_end", "total_return", "annualized_return",
                    "n_periods", "python_version", "env_fingerprint", "data_fingerprint", "deps_json")
# Columns added by research_lab._ensure_columns after the table was first published.
LATE_COLUMNS = {"deps_json", "python_version", "env_fingerprint", "data_fingerprint"}


class SqliteExperiments:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def _connect(self):
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        return closing(db)

    @staticmethod
    def _columns(db, wanted: tuple[str, ...]) -> str | None:
        present = {row[1] for row in db.execute("PRAGMA table_info(experiments)")}
        if not present:
            return None
        missing = set(wanted) - present
        if missing - LATE_COLUMNS:
            raise QueryError("experiments_invalid", "El registro de experimentos está incompleto.", 503)
        return ",".join(name if name in present else f"NULL AS {name}" for name in wanted)

    def _read(self, action):
        if not self.path.is_file():
            return None
        try:
            with self._connect() as db:
                return action(db)
        except sqlite3.Error as exc:
            raise QueryError("experiments_unavailable", "No se puede leer el registro de experimentos.", 503) from exc

    def list(self, family: str | None, stage: str | None) -> tuple[list[dict], list[str]]:
        """All matching summaries, newest first, as research_lab.list_experiments ordered them."""
        def action(db):
            columns = self._columns(db, SUMMARY)
            if columns is None:
                return [], []
            conditions, params = [], []
            if family is not None:
                conditions.append("family = ?")
                params.append(family)
            if stage is not None:
                conditions.append("stage = ?")
                params.append(stage)
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            rows = db.execute(
                f"SELECT {columns}, returns_json IS NOT NULL AS has_returns, "
                f"length(notes) > ? AS notes_too_long FROM experiments{where} ORDER BY id DESC LIMIT ?",
                (MAX_TEXT_CHARS, *params, MAX_EXPERIMENTS + 1)).fetchall()
            if len(rows) > MAX_EXPERIMENTS:
                raise QueryError("experiments_limit", "Hay demasiados experimentos para esta consulta.", 503)
            if any(row["notes_too_long"] for row in rows):
                raise QueryError("experiments_limit", "Unas notas superan el límite de lectura.", 503)
            families = [row[0] for row in db.execute(
                "SELECT DISTINCT family FROM experiments WHERE family IS NOT NULL ORDER BY family")]
            items = []
            for row in rows:
                item = {key: row[key] for key in SUMMARY}
                item["has_returns"] = bool(row["has_returns"])
                items.append(item)
            return items, families

        return self._read(action) or ([], [])

    def get(self, experiment_id: int) -> dict | None:
        """One experiment with its environment and saved return series (bounded)."""
        def action(db):
            columns = self._columns(db, DETAIL)
            if columns is None:
                return None
            row = db.execute(
                f"SELECT {columns}, length(returns_json) AS returns_chars, "
                "CASE WHEN length(returns_json) <= ? THEN returns_json END AS returns_json, "
                "CASE WHEN json_valid(result_json) THEN json_extract(result_json,'$.backtest_job_id') END "
                "AS backtest_job_id FROM experiments WHERE id = ?",
                (MAX_RETURNS_CHARS, experiment_id)).fetchone()
            if row is None:
                return None
            if row["returns_chars"] is not None and row["returns_chars"] > MAX_RETURNS_CHARS:
                raise QueryError("experiments_limit", "La serie del experimento supera el límite de lectura.", 503)
            if any(isinstance(row[key], str) and len(row[key]) > MAX_TEXT_CHARS
                   for key in DETAIL):
                raise QueryError("experiments_limit", "Un campo del experimento supera el límite de lectura.", 503)
            item = {key: row[key] for key in DETAIL if not key.endswith("_json")}
            try:
                item["weights"] = json.loads(row["weights_json"]) if row["weights_json"] else None
                item["deps"] = json.loads(row["deps_json"]) if row["deps_json"] else None
                item["returns"] = json.loads(row["returns_json"]) if row["returns_json"] else None
            except ValueError as exc:
                raise QueryError("experiments_invalid", "Un experimento tiene JSON no válido.", 503) from exc
            item["backtest_job_id"] = row["backtest_job_id"]
            return item

        return self._read(action)
