"""Aggregate estimate capture coverage without initializing or changing SQLite."""

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.research.reservations import OBSERVED_START, require_observed_period
from gabi.infrastructure.storage.factor_prices import SqliteFactorPrices

MAX_ANALYSIS_BATCHES = 64
MAX_ANALYSIS_SYMBOLS_PER_BATCH = 1_000


class SqliteEstimateCaptures:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"

    def coverage(self, period: str, min_symbols: int) -> dict:
        empty = {"batches_total": 0, "batches_eligible": 0,
                 "first_eligible": None, "last_eligible": None}
        if not self.path.is_file():
            return empty
        try:
            db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
            with closing(db):
                db.execute("PRAGMA query_only=ON")
                exists = db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' "
                                    "AND name='estimate_snapshots'").fetchone()
                if exists is None:
                    return empty
                row = db.execute("""
                    WITH batches AS (
                        SELECT captured_at, COUNT(DISTINCT symbol) AS n_symbols
                        FROM estimate_snapshots WHERE period=? GROUP BY captured_at
                    )
                    SELECT COUNT(*),
                           COUNT(CASE WHEN n_symbols >= ? THEN 1 END),
                           MIN(CASE WHEN n_symbols >= ? THEN captured_at END),
                           MAX(CASE WHEN n_symbols >= ? THEN captured_at END)
                    FROM batches
                """, (period, min_symbols, min_symbols, min_symbols)).fetchone()
                return dict(zip(empty, row, strict=True))
        except sqlite3.Error as exc:
            raise QueryError("estimate_data_unavailable", "No se pueden leer las capturas de estimaciones.",
                             503) from exc


class SqliteEstimateAnalysis:
    """Bounded inputs for an explicit observed-period analysis job."""

    def __init__(self, data_dir: Path, cutoff: date):
        require_observed_period(cutoff.isoformat())
        self.path = data_dir / "gabi.db"
        self.cutoff = cutoff
        self.prices = SqliteFactorPrices(data_dir)

    def batches(self, period: str) -> pd.DataFrame:
        columns = ["captured_at", "n_symbols"]
        if not self.path.is_file():
            return pd.DataFrame(columns=columns)
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            exists = db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' "
                                "AND name='estimate_snapshots'").fetchone()
            if exists is None:
                return pd.DataFrame(columns=columns)
            rows = db.execute("""
                SELECT captured_at, COUNT(DISTINCT symbol) AS n_symbols
                FROM estimate_snapshots
                WHERE period=? AND captured_at>=? AND captured_at<?
                GROUP BY captured_at ORDER BY captured_at LIMIT ?
            """, (period, OBSERVED_START.isoformat(),
                  date.fromordinal(self.cutoff.toordinal() + 1).isoformat(),
                  MAX_ANALYSIS_BATCHES + 1)).fetchall()
        if len(rows) > MAX_ANALYSIS_BATCHES or any(row[1] > MAX_ANALYSIS_SYMBOLS_PER_BATCH for row in rows):
            raise ValueError("Las capturas superan el límite del análisis de estimaciones.")
        return pd.DataFrame(rows, columns=columns)

    def rows(self, period: str, captures: list[str]) -> pd.DataFrame:
        columns = ["symbol", "captured_at", "revised_up_30d", "revised_down_30d"]
        if not captures:
            return pd.DataFrame(columns=columns)
        if len(captures) > MAX_ANALYSIS_BATCHES or len(set(captures)) != len(captures):
            raise ValueError("Demasiadas capturas para el análisis.")
        marks = ",".join("?" for _ in captures)
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute(
                f"SELECT symbol,captured_at,revised_up_30d,revised_down_30d FROM estimate_snapshots "
                f"WHERE period=? AND captured_at IN ({marks}) ORDER BY captured_at,symbol LIMIT ?",
                (period, *captures, MAX_ANALYSIS_BATCHES * MAX_ANALYSIS_SYMBOLS_PER_BATCH + 1),
            ).fetchall()
        if len(rows) > MAX_ANALYSIS_BATCHES * MAX_ANALYSIS_SYMBOLS_PER_BATCH:
            raise ValueError("Las filas superan el límite del análisis de estimaciones.")
        return pd.DataFrame(rows, columns=columns)

    def prices_for_sessions(self, symbols: list[str], first: str, last: str) -> dict:
        require_observed_period(first, last)
        return self.prices(symbols, first, last)


SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS estimate_snapshots (
    symbol TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    period TEXT NOT NULL,
    eps_avg REAL, eps_low REAL, eps_high REAL, eps_analysts INTEGER,
    eps_dispersion_pct REAL,
    revenue_avg REAL, revenue_low REAL, revenue_high REAL,
    revised_up_7d INTEGER, revised_down_7d INTEGER,
    revised_up_30d INTEGER, revised_down_30d INTEGER,
    source TEXT NOT NULL,
    PRIMARY KEY (symbol, captured_at, period)
);
"""


def store_estimate_snapshot(data_dir: Path, rows: list[dict]) -> None:
    """Explicit write of one capture (``captured_at`` is the real capture time); replaces the same key."""
    if not rows:
        return
    with closing(sqlite3.connect(data_dir / "gabi.db", timeout=30)) as db:
        db.executescript(SNAPSHOTS)
        db.executemany(
            "INSERT OR REPLACE INTO estimate_snapshots "
            "(symbol, captured_at, period, eps_avg, eps_low, eps_high, eps_analysts, eps_dispersion_pct, "
            "revenue_avg, revenue_low, revenue_high, revised_up_7d, revised_down_7d, revised_up_30d, "
            "revised_down_30d, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r["symbol"], r["captured_at"], r["period"], r["eps_avg"], r["eps_low"], r["eps_high"],
              r["eps_analysts"], r["eps_dispersion_pct"], r["revenue_avg"], r["revenue_low"], r["revenue_high"],
              r["revised_up_7d"], r["revised_down_7d"], r["revised_up_30d"], r["revised_down_30d"], r["source"])
             for r in rows],
        )
        db.commit()
