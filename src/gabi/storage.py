"""Capa de persistencia en SQLite para precios y fundamentales cacheados."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import pandas as pd

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS fundamentals (
    symbol TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    info_json TEXT NOT NULL,
    quarterly_income_json TEXT NOT NULL,
    quarterly_cashflow_json TEXT NOT NULL
);
"""


@contextmanager
def get_connection():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def _df_to_json(df):
    """Serializa un DataFrame de estado financiero (filas=partida, columnas=fecha)
    a JSON como dict[fecha_str][partida] = valor."""
    if df is None or df.empty:
        return "{}"
    d = df.T
    d.index = d.index.astype(str)
    d = d.apply(pd.to_numeric, errors="coerce")
    return json.dumps(d.to_dict(orient="index"))


def upsert_prices(symbol: str, price_df: pd.DataFrame):
    """price_df: DataFrame indexado por fecha con columnas Open/High/Low/Close/Volume
    (formato nativo de yfinance)."""
    if price_df is None or price_df.empty:
        return
    df = price_df.copy().reset_index()
    df.rename(columns={df.columns[0]: "date"}, inplace=True)
    records = []
    for row in df.itertuples(index=False):
        d = row.date
        date_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        records.append((
            symbol, date_str,
            float(row.Open) if pd.notna(row.Open) else None,
            float(row.High) if pd.notna(row.High) else None,
            float(row.Low) if pd.notna(row.Low) else None,
            float(row.Close) if pd.notna(row.Close) else None,
            float(row.Volume) if pd.notna(row.Volume) else None,
        ))
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO prices (symbol, date, open, high, low, close, volume) "
            "VALUES (?,?,?,?,?,?,?)", records,
        )
        conn.commit()


def get_prices(symbol: str) -> pd.DataFrame:
    """Devuelve DataFrame indexado por fecha (ascendente) con columnas
    open/high/low/close/volume para un símbolo."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM prices "
            "WHERE symbol = ? ORDER BY date ASC",
            conn, params=(symbol,),
        )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def get_prices_multi(symbols: list) -> dict:
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        df = pd.read_sql_query(
            f"SELECT symbol, date, open, high, low, close, volume FROM prices "
            f"WHERE symbol IN ({placeholders}) ORDER BY date ASC",
            conn, params=symbols,
        )
    result = {}
    if df.empty:
        return result
    df["date"] = pd.to_datetime(df["date"])
    for sym, group in df.groupby("symbol"):
        result[sym] = group.drop(columns=["symbol"]).set_index("date")
    return result


def get_latest_price_date(symbols: list = None):
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        if symbols:
            placeholders = ",".join("?" * len(symbols))
            row = conn.execute(
                f"SELECT MAX(date) FROM prices WHERE symbol IN ({placeholders})", symbols,
            ).fetchone()
        else:
            row = conn.execute("SELECT MAX(date) FROM prices").fetchone()
    if not row or not row[0]:
        return None
    return datetime.strptime(row[0], "%Y-%m-%d").date()


def upsert_fundamentals(symbol: str, info: dict, quarterly_income_df, quarterly_cashflow_df):
    fetched_at = datetime.now(timezone.utc).isoformat()
    payload = (
        symbol, fetched_at,
        json.dumps(info),
        _df_to_json(quarterly_income_df),
        _df_to_json(quarterly_cashflow_df),
    )
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO fundamentals "
            "(symbol, fetched_at, info_json, quarterly_income_json, quarterly_cashflow_json) "
            "VALUES (?,?,?,?,?)", payload,
        )
        conn.commit()


def get_fundamentals(symbols: list) -> dict:
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute(
            f"SELECT symbol, fetched_at, info_json, quarterly_income_json, quarterly_cashflow_json "
            f"FROM fundamentals WHERE symbol IN ({placeholders})", symbols,
        ).fetchall()
    result = {}
    for symbol, fetched_at, info_json, qi_json, qcf_json in rows:
        result[symbol] = {
            "fetched_at": fetched_at,
            "info": json.loads(info_json),
            "quarterly_income": json.loads(qi_json),
            "quarterly_cashflow": json.loads(qcf_json),
        }
    return result


def get_fundamentals_fetched_at(symbols: list) -> dict:
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute(
            f"SELECT symbol, fetched_at FROM fundamentals WHERE symbol IN ({placeholders})", symbols,
        ).fetchall()
    result = {}
    for symbol, fetched_at in rows:
        try:
            result[symbol] = datetime.fromisoformat(fetched_at)
        except Exception:
            result[symbol] = None
    return result
