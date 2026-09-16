"""Guarda candidatas rankeadas y evalúa más adelante su rentabilidad total frente al SPY."""
import sqlite3
from datetime import date

import pandas as pd

from . import storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS ranking_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    source TEXT NOT NULL,
    symbol TEXT NOT NULL,
    rank INTEGER NOT NULL,
    score REAL NOT NULL,
    coverage REAL NOT NULL
);
"""


def save_snapshot(table: pd.DataFrame, as_of_date: str, source: str = "live", top_n: int = 10) -> int:
    """Guarda solo las filas rankeadas con cobertura suficiente; devuelve el id del snapshot."""
    candidates = table[table["composite_score"].notna()].head(top_n)
    if candidates.empty:
        return 0
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        snapshot_id = conn.execute("SELECT COALESCE(MAX(snapshot_id), 0) + 1 FROM ranking_snapshots").fetchone()[0]
        conn.executemany(
            "INSERT INTO ranking_snapshots (snapshot_id, created_at, as_of_date, source, symbol, rank, score, coverage) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(snapshot_id, date.today().isoformat(), as_of_date, source, symbol, rank,
              float(row.composite_score), float(row.score_coverage))
             for rank, (symbol, row) in enumerate(candidates.iterrows(), 1)],
        )
        conn.commit()
    return snapshot_id


def list_snapshots() -> pd.DataFrame:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        return pd.read_sql_query(
            "SELECT snapshot_id AS id, created_at, as_of_date, source, COUNT(*) AS candidates "
            "FROM ranking_snapshots GROUP BY snapshot_id, created_at, as_of_date, source ORDER BY snapshot_id DESC", conn,
        )


def snapshot_symbols(snapshot_id: int) -> list[str]:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        return [r[0] for r in conn.execute(
            "SELECT symbol FROM ranking_snapshots WHERE snapshot_id=? ORDER BY rank", (snapshot_id,)
        )]


def _adjusted_at(symbol: str, target: pd.Timestamp, after: bool = False):
    prices = storage.get_prices(symbol)
    if prices.empty or "adj_close" not in prices:
        return None
    values = prices["adj_close"].dropna()
    if after:
        values = values[(values.index >= target) & (values.index <= target + pd.Timedelta(days=7))]
        return float(values.iloc[0]) if not values.empty else None
    values = values[(values.index <= target) & (values.index >= target - pd.Timedelta(days=7))]
    return float(values.iloc[-1]) if not values.empty else None


def evaluate(symbols: list[str], as_of_date: str, months: int = 6, cost_bps: float = 0) -> dict:
    """Rentabilidad total con el mismo peso por candidata, incluyendo el coste de ida y vuelta; los datos que faltan nunca cuentan como cero."""
    start = pd.Timestamp(as_of_date)
    end = start + pd.DateOffset(months=months)
    if end > pd.Timestamp(date.today()):
        return {"status": "pending", "end_date": end.date().isoformat()}
    returns = {}
    for symbol in dict.fromkeys(symbols):
        p0 = _adjusted_at(symbol, start)
        p1 = _adjusted_at(symbol, end, after=True)
        if p0 and p1:
            returns[symbol] = p1 / p0 - 1 - 2 * cost_bps / 10000
    b0 = _adjusted_at("SPY", start)
    b1 = _adjusted_at("SPY", end, after=True)
    benchmark = b1 / b0 - 1 - 2 * cost_bps / 10000 if b0 and b1 else None
    portfolio = sum(returns.values()) / len(returns) if returns else None
    return {
        "status": "complete" if len(returns) == len(set(symbols)) and benchmark is not None else "incomplete",
        "end_date": end.date().isoformat(), "available": len(returns), "requested": len(set(symbols)),
        "portfolio_return": portfolio, "benchmark_return": benchmark,
        "excess_return": portfolio - benchmark if portfolio is not None and benchmark is not None else None,
        "missing": sorted(set(symbols) - returns.keys()),
    }
