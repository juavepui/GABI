"""Capa de persistencia en SQLite para precios y fundamentales cacheados."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pandas as pd

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    adj_close REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS fundamentals (
    symbol TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    info_json TEXT NOT NULL,
    quarterly_income_json TEXT NOT NULL,
    quarterly_cashflow_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS splits (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    ratio REAL NOT NULL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS update_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    symbol TEXT,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_update_errors_source_time ON update_errors (source, occurred_at);
"""

UPDATE_ERRORS_RETENTION_DAYS = 90


@contextmanager
def get_connection():
    """Única función de todo el proyecto que abre una conexión SQLite (todos
    los módulos pasan por aquí, incluido `storage.py` mismo) — así que el
    modo WAL y el timeout se aplican en un solo sitio, no en cada llamador.

    `timeout=30`: SQLite reintenta adquirir el lock hasta 30s (el default de
    Python son solo 5s) antes de lanzar `sqlite3.OperationalError: database
    is locked` — cubre con margen una escritura larga concurrente (ej. dos
    pestañas del navegador, o una sesión de Streamlit que quedó a medias)
    sin fallar de inmediato. `PRAGMA journal_mode=WAL`: permite que lecturas
    y escrituras no se bloqueen mutuamente (a diferencia del modo por
    defecto, donde una escritura bloquea todas las lecturas) — comprobado
    con datos reales que esto era la causa de un "database is locked" real
    con varias sesiones de Streamlit abiertas a la vez sobre el mismo
    fichero. El modo WAL queda grabado en el propio fichero .db, así que
    poner el PRAGMA en cada conexión es barato (no-op si ya estaba activo)."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_price_columns(conn)
        conn.commit()


def _ensure_price_columns(conn):
    if "adj_close" not in {row[1] for row in conn.execute("PRAGMA table_info(prices)")}:
        conn.execute("ALTER TABLE prices ADD COLUMN adj_close REAL")


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
    df.rename(columns={"Adj Close": "Adj_Close"}, inplace=True)
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
            float(row.Adj_Close) if hasattr(row, "Adj_Close") and pd.notna(row.Adj_Close) else None,
        ))
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_price_columns(conn)
        conn.executemany(
            "INSERT OR REPLACE INTO prices (symbol, date, open, high, low, close, volume, adj_close) "
            "VALUES (?,?,?,?,?,?,?,?)", records,
        )
        conn.commit()


def get_prices(symbol: str) -> pd.DataFrame:
    """Devuelve DataFrame indexado por fecha (ascendente) con columnas
    open/high/low/close/volume para un símbolo."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_price_columns(conn)
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume, adj_close FROM prices "
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
        _ensure_price_columns(conn)
        df = pd.read_sql_query(
            f"SELECT symbol, date, open, high, low, close, volume, adj_close FROM prices "
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


def get_price_coverage(symbols: list) -> dict:
    """Nº de cierres ajustados verificados y su fecha más reciente, en una sola consulta a la base de datos."""
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_price_columns(conn)
        rows = conn.execute(
            f"SELECT symbol, COUNT(adj_close), MAX(CASE WHEN adj_close IS NOT NULL THEN date END) "
            f"FROM prices WHERE symbol IN ({placeholders}) GROUP BY symbol", symbols,
        ).fetchall()
    return {symbol: {"adjusted_count": count, "latest_adjusted_date": latest}
            for symbol, count, latest in rows}


def get_price_as_of(symbol: str, as_of_date: str):
    """Precio de cierre más reciente en/antes de as_of_date (YYYY-MM-DD) —
    el de ese día si es sesión de mercado, si no el de la sesión anterior
    más cercana. None si no hay precio cacheado tan atrás en el tiempo (el
    histórico de precios solo cubre ~2 años desde la última actualización,
    así que fechas más antiguas pueden no tener dato disponible)."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        row = conn.execute(
            "SELECT close FROM prices WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1",
            (symbol, as_of_date),
        ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def has_verified_price_as_of(symbol: str, as_of_date: str) -> bool:
    """True si hay un cierre ajustado (adj_close) verificado para esa fecha; False si el precio en caché es de antes de este cambio y todavía no lo tiene."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_price_columns(conn)
        row = conn.execute(
            "SELECT adj_close FROM prices WHERE symbol=? AND date<=? ORDER BY date DESC LIMIT 1",
            (symbol, as_of_date),
        ).fetchone()
    return bool(row and row[0] is not None)


def upsert_splits(symbol: str, splits: dict):
    """splits: {fecha_iso: ratio} — ej. {'2020-08-31': 4.0} para un split 4:1."""
    if not splits:
        return
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO splits (symbol, date, ratio) VALUES (?,?,?)",
            [(symbol, d, r) for d, r in splits.items()],
        )
        conn.commit()


def get_split_factor_since(symbol: str, as_of_date: str) -> float:
    """Producto de todos los splits de `symbol` ocurridos DESPUÉS de
    as_of_date. yfinance devuelve el precio siempre ajustado por splits
    (con o sin auto_adjust) — para calcular la capitalización de una fecha
    pasada con el nº de acciones REAL de esa fecha (sin ajustar, tal y como
    lo reporta SEC EDGAR), hay que multiplicar el precio ajustado por este
    factor para deshacer los splits posteriores a esa fecha. 1.0 si no hubo
    ningún split después (o no hay splits registrados)."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute(
            "SELECT ratio FROM splits WHERE symbol = ? AND date > ?", (symbol, as_of_date),
        ).fetchall()
    factor = 1.0
    for (ratio,) in rows:
        if ratio:
            factor *= ratio
    return factor


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
    fetched_at = datetime.now(UTC).isoformat()
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


def record_update_errors(source: str, failed: dict):
    """Persiste los fallos de una actualización (`failed`: {symbol_o_series:
    motivo}) -- antes de esto, `ensure_*` de data_fetch/edgar/insider/macro
    solo devolvía `failed` como valor de retorno, así que se mostraba una
    vez tras pulsar 'Actualizar datos' y se perdía; no había forma de saber
    después qué había fallado en el último refresco. No-op si `failed` está
    vacío. Poda entradas de más de `UPDATE_ERRORS_RETENTION_DAYS` en cada
    llamada -- suficiente para una tabla de uso personal, sin mecanismo de
    limpieza aparte."""
    if not failed:
        return
    occurred_at = datetime.now(UTC).isoformat()
    cutoff = (datetime.now(UTC) - timedelta(days=UPDATE_ERRORS_RETENTION_DAYS)).isoformat()
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO update_errors (source, symbol, reason, occurred_at) VALUES (?,?,?,?)",
            [(source, symbol, str(reason), occurred_at) for symbol, reason in failed.items()],
        )
        conn.execute("DELETE FROM update_errors WHERE occurred_at < ?", (cutoff,))
        conn.commit()


def get_recent_update_errors(source: str = None, since_hours: float = 24 * 7) -> pd.DataFrame:
    """Fallos de actualización de los últimos `since_hours` (por defecto, 7
    días), opcionalmente filtrados por fuente ('yahoo_precio',
    'yahoo_fundamentales', 'sec_edgar', 'insider_form4', 'fred_macro')."""
    cutoff = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()
    query = "SELECT source, symbol, reason, occurred_at FROM update_errors WHERE occurred_at >= ?"
    params: list = [cutoff]
    if source:
        query += " AND source = ?"
        params.append(source)
    query += " ORDER BY occurred_at DESC"
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        return pd.read_sql_query(query, conn, params=params)
