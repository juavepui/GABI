"""Read-only earnings surprises and consensus-estimate history of one company (never initializes tables)."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from gabi.application.errors import QueryError

MAX_SURPRISES = 200
MAX_ESTIMATES = 5_000
SURPRISE_COLUMNS = ("earnings_date", "eps_estimate", "eps_reported", "surprise_pct", "price_reaction_pct",
                    "source", "recorded_at")
ESTIMATE_COLUMNS = ("captured_at", "period", "eps_avg", "eps_low", "eps_high", "eps_analysts", "eps_dispersion_pct",
                    "revenue_avg", "revenue_low", "revenue_high", "revised_up_7d", "revised_down_7d",
                    "revised_up_30d", "revised_down_30d", "source")


class SqliteCompanyResearch:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def _frame(self, table: str, columns: tuple[str, ...], where: str, params: tuple, order: str,
               limit: int) -> pd.DataFrame:
        if not self.path.is_file():
            return pd.DataFrame(columns=list(columns))
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone() is None:
                    return pd.DataFrame(columns=list(columns))
                rows = db.execute(f"SELECT {','.join(columns)} FROM {table} WHERE {where} ORDER BY {order} LIMIT ?",
                                  (*params, limit + 1)).fetchall()
        except sqlite3.Error as exc:
            raise QueryError("data_read_error", "No se pueden consultar los datos de la empresa.", 503) from exc
        if len(rows) > limit:
            raise QueryError("resource_limit", "El historial de la empresa supera el límite de lectura.", 503)
        return pd.DataFrame(rows, columns=list(columns))

    def surprises(self, symbol: str) -> pd.DataFrame:
        """As events_calendar.get_earnings_surprises: newest first."""
        return self._frame("earnings_surprises", SURPRISE_COLUMNS, "symbol=?", (symbol,), "earnings_date DESC",
                           MAX_SURPRISES)

    def estimate_history(self, symbol: str, period: str) -> pd.DataFrame:
        """As estimates.get_estimate_history: the captures GABI kept, oldest first."""
        return self._frame("estimate_snapshots", ESTIMATE_COLUMNS, "symbol=? AND period=?", (symbol, period),
                           "captured_at ASC", MAX_ESTIMATES)
