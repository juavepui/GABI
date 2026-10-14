"""Capa de persistencia en SQLite para precios y fundamentales cacheados."""
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

import pandas as pd

from gabi.application.market import cached_data
from gabi.infrastructure.storage import cache_writes
from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
from gabi.infrastructure.storage.cache_writes import SqliteCacheWrites

from . import config

SCHEMA = cache_writes.SCHEMA

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


def _writer() -> SqliteCacheWrites:
    # The compatibility path is captured per operation, never mutated.
    return SqliteCacheWrites(config.DB_PATH, lambda: datetime.now(UTC), error_retention_days=UPDATE_ERRORS_RETENTION_DAYS)


def init_db():
    _writer().initialize()


_ensure_price_columns = cache_writes.ensure_price_columns
_df_to_json = cache_writes.statement_json


def upsert_prices(symbol: str, price_df: pd.DataFrame, *, entity_id: str | None = None):
    """price_df: DataFrame indexado por fecha con columnas Open/High/Low/Close/Volume
    (formato nativo de yfinance)."""
    _writer().prices(symbol, price_df, entity_id=entity_id)


def _reader() -> SqliteCacheReads:
    # The compatibility setting is captured per operation, never mutated.
    return SqliteCacheReads(config.DB_PATH)


def get_prices(symbol: str) -> pd.DataFrame:
    """Devuelve DataFrame indexado por fecha (ascendente) con columnas
    open/high/low/close/volume para un símbolo."""
    return cached_data.prices(_reader(), symbol)


def get_prices_multi(symbols: list) -> dict:
    return cached_data.prices_multi(_reader(), symbols)


def get_price_coverage(symbols: list) -> dict:
    """Nº de cierres ajustados verificados y su fecha más reciente, por lotes en una transacción de lectura."""
    return cached_data.price_coverage(_reader(), symbols)


def get_price_as_of(symbol: str, as_of_date: str):
    """Precio de cierre más reciente en/antes de as_of_date (YYYY-MM-DD) —
    el de ese día si es sesión de mercado, si no el de la sesión anterior
    más cercana. None si no hay precio cacheado tan atrás en el tiempo (el
    histórico de precios solo cubre ~2 años desde la última actualización,
    así que fechas más antiguas pueden no tener dato disponible)."""
    return cached_data.price_as_of(_reader(), symbol, as_of_date)


def has_verified_price_as_of(symbol: str, as_of_date: str) -> bool:
    """True si hay un cierre ajustado (adj_close) verificado para esa fecha; False si el precio en caché es de antes de este cambio y todavía no lo tiene."""
    return cached_data.has_verified_price_as_of(_reader(), symbol, as_of_date)


def upsert_splits(symbol: str, splits: dict, *, entity_id: str | None = None):
    """splits: {fecha_iso: ratio} — ej. {'2020-08-31': 4.0} para un split 4:1."""
    _writer().splits(symbol, splits, entity_id=entity_id)


def get_split_factor_since(symbol: str, as_of_date: str) -> float:
    """Producto de todos los splits de `symbol` ocurridos DESPUÉS de
    as_of_date. yfinance devuelve el precio siempre ajustado por splits
    (con o sin auto_adjust) — para calcular la capitalización de una fecha
    pasada con el nº de acciones REAL de esa fecha (sin ajustar, tal y como
    lo reporta SEC EDGAR), hay que multiplicar el precio ajustado por este
    factor para deshacer los splits posteriores a esa fecha. 1.0 si no hubo
    ningún split después (o no hay splits registrados)."""
    return cached_data.split_factor_since(_reader(), symbol, as_of_date)


def upsert_fundamentals(symbol: str, info: dict, quarterly_income_df, quarterly_cashflow_df,
                        *, entity_id: str | None = None):
    _writer().fundamentals(symbol, info, quarterly_income_df, quarterly_cashflow_df, entity_id=entity_id)


def get_fundamentals(symbols: list) -> dict:
    return cached_data.fundamentals(_reader(), symbols)


def get_fundamentals_fetched_at(symbols: list) -> dict:
    return cached_data.fundamentals_fetched_at(_reader(), symbols)


def record_update_errors(source: str, failed: dict):
    """Persiste los fallos de una actualización (`failed`: {symbol_o_series:
    motivo}) -- antes de esto, `ensure_*` de data_fetch/edgar/insider/macro
    solo devolvía `failed` como valor de retorno, así que se mostraba una
    vez tras pulsar 'Actualizar datos' y se perdía; no había forma de saber
    después qué había fallado en el último refresco. No-op si `failed` está
    vacío. Poda entradas de más de `UPDATE_ERRORS_RETENTION_DAYS` en cada
    llamada -- suficiente para una tabla de uso personal, sin mecanismo de
    limpieza aparte."""
    _writer().update_errors(source, failed)


def get_recent_update_errors(source: str = None, since_hours: float = 24 * 7) -> pd.DataFrame:
    """Fallos de actualización de los últimos `since_hours` (por defecto, 7
    días), opcionalmente filtrados por fuente ('yahoo_precio',
    'yahoo_fundamentales', 'sec_edgar', 'insider_form4', 'fred_macro')."""
    return cached_data.recent_update_errors(_reader(), now=datetime.now(UTC), source=source, since_hours=since_hours)
