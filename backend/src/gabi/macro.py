"""Contexto macroeconómico vía la API de FRED (Federal Reserve Economic Data).

A diferencia de yfinance y SEC EDGAR, FRED requiere una API key gratuita
(sin tarjeta, alta inmediata en https://fred.stlouisfed.org/docs/api/api_key.html).
Sin clave configurada, todo esto se degrada con elegancia: ensure_macro_data
devuelve ok=False y la página explica cómo conseguirla, en vez de fallar.

El objetivo no es meter macro en el score (eso ya es terreno de "qué factor
funciona bajo qué régimen", que requiere el backtesting que se decidió NO
construir todavía) sino tener a mano, al escribir una tesis en el Diario de
inversión, las relaciones causales típicas: tipos, inflación, curva, crédito..."""
from datetime import UTC, date, datetime

import pandas as pd
import requests

from gabi.application.administration.fred import synchronize
from gabi.domain.market import fred

from . import config, storage
from .data_fetch import _classify_error

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# id FRED -> metadatos. units_param sigue la convención de la API de FRED
# ("lin" = sin transformar, "pc1" = variación % interanual).
SERIES = {key: dict(value) for key, value in fred.SERIES.items()}

SCHEMA = """
CREATE TABLE IF NOT EXISTS macro_series (
    series_id TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (series_id, date)
);
CREATE TABLE IF NOT EXISTS macro_meta (
    series_id TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL
);
"""


def fetch_series(series_id: str, api_key: str, units: str = "lin", limit: int = 260,
                 *, observation_start: str | None = None, include_missing: bool = False) -> list:
    """[(fecha, valor), ...] más reciente primero. Descarta observaciones sin
    dato ('.' es como FRED marca los huecos)."""
    params = {
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "sort_order": "desc", "limit": limit, "units": units,
    }
    if observation_start:
        params["observation_start"] = observation_start
    resp = requests.get(FRED_BASE_URL, params=params, timeout=20)
    if resp.status_code in (400, 401, 403):
        raise ValueError("FRED ha rechazado la petición (revisa que la API key sea correcta)")
    resp.raise_for_status()
    data = resp.json()
    return fred.observations(data, include_missing=include_missing)


def upsert_series(series_id: str, observations: list):
    fetched_at = datetime.now(UTC).isoformat()
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO macro_series (series_id, date, value) VALUES (?,?,?)",
            [(series_id, date, value) for date, value in observations],
        )
        conn.execute(
            "INSERT OR REPLACE INTO macro_meta (series_id, fetched_at) VALUES (?,?)",
            (series_id, fetched_at),
        )
        conn.commit()


def get_series_history(series_id: str) -> pd.DataFrame:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        df = pd.read_sql_query(
            "SELECT date, value FROM macro_series WHERE series_id = ? ORDER BY date ASC",
            conn, params=(series_id,),
        )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def get_all_fetched_at() -> dict:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute("SELECT series_id, fetched_at FROM macro_meta").fetchall()
    result = {}
    for series_id, fetched_at in rows:
        try:
            result[series_id] = datetime.fromisoformat(fetched_at)
        except Exception:
            result[series_id] = None
    return result


class _Repository:
    def fetched_at(self, series_ids):
        return get_all_fetched_at()

    def failed(self, series_ids):
        from . import sync_state

        return {entity for entity, _ in sync_state.failed_datasets("fred")}

    def history(self, series_id):
        return get_series_history(series_id)

    def upsert(self, series_id, observations):
        upsert_series(series_id, observations)

    def record_errors(self, failed):
        storage.record_update_errors("fred_macro", failed)


def ensure_macro_data(force: bool = False, max_age_hours: int = 24, progress_cb=None,
                      *, full_refresh: bool = False) -> dict:
    from . import sync_state as sync

    return synchronize(_Repository(), SERIES, config.load_fred_key,
                       fetch_series, sync.get, sync.Attempt, sync.retry,
                       lambda exc: _classify_error(exc, service="FRED")[1],
                       lambda: datetime.now(UTC), force=force, max_age_hours=max_age_hours,
                       full_refresh=full_refresh, progress_cb=progress_cb)


# release_id de FRED (no de series) -- solo para series que representan una
# publicación programada y discreta (una vez al mes, en fecha conocida de
# antemano), no una serie que se actualiza a diario como DGS10 o FEDFUNDS:
# ahí "próxima actualización" no es un evento, es continuo.
RELEASE_IDS = {"CPIAUCSL": 10}
RELEASE_DATES_URL = "https://api.stlouisfed.org/fred/release/dates"


_parse_next_release_date = fred.parse_next_release_date

def fetch_next_release_date(series_id: str, api_key: str) -> date | None:
    """Próxima fecha de publicación programada (confirmada por la fuente
    oficial que FRED indexa, ej. BLS para CPI) -- None si `series_id` no
    tiene un release_id mapeado en RELEASE_IDS o si FRED no devuelve ninguna
    fecha futura."""
    release_id = RELEASE_IDS.get(series_id)
    if release_id is None:
        return None
    today = date.today()
    params = {
        "release_id": release_id, "api_key": api_key, "file_type": "json",
        "realtime_start": today.isoformat(), "sort_order": "asc",
        "include_release_dates_with_no_data": "true",
    }
    resp = requests.get(RELEASE_DATES_URL, params=params, timeout=20)
    resp.raise_for_status()
    return _parse_next_release_date(resp.json(), today)


def get_snapshot() -> pd.DataFrame:
    return fred.snapshot(SERIES, {sid: get_series_history(sid) for sid in SERIES})
