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

from gabi.application.administration.fred import synchronize
from gabi.domain.market import fred
from gabi.domain.market.source_errors import classify
from gabi.infrastructure.providers.fred import FredSource
from gabi.infrastructure.storage.fred import SCHEMA as SCHEMA
from gabi.infrastructure.storage.fred import SqliteFred

from . import config

# id FRED -> metadatos. units_param sigue la convención de la API de FRED
# ("lin" = sin transformar, "pc1" = variación % interanual).
SERIES = {key: dict(value) for key, value in fred.SERIES.items()}



def fetch_series(series_id: str, api_key: str, units: str = "lin", limit: int = 260,
                 *, observation_start: str | None = None, include_missing: bool = False) -> list:
    """[(fecha, valor), ...] más reciente primero. Descarta observaciones sin
    dato ('.' es como FRED marca los huecos)."""
    return FredSource().fetch(series_id, api_key, units, limit, observation_start=observation_start,
                              include_missing=include_missing, require_complete=False)


def _repository() -> SqliteFred:
    # The compatibility path is captured per operation, never mutated.
    return SqliteFred(config.DB_PATH, lambda: datetime.now(UTC))


def upsert_series(series_id: str, observations: list):
    _repository().upsert(series_id, observations)


def get_series_history(series_id: str) -> pd.DataFrame:
    return _repository().history(series_id)


def get_all_fetched_at() -> dict:
    return _repository().fetched_at_all()


def ensure_macro_data(force: bool = False, max_age_hours: int = 24, progress_cb=None,
                      *, full_refresh: bool = False) -> dict:
    from . import sync_state as sync

    return synchronize(_repository(), SERIES, config.load_fred_key,
                       fetch_series, sync.get, sync.Attempt, sync.retry,
                       lambda exc: classify(str(exc), "FRED")[1],
                       lambda: datetime.now(UTC), force=force, max_age_hours=max_age_hours,
                       full_refresh=full_refresh, progress_cb=progress_cb)


# release_id de FRED (no de series) -- solo para series que representan una
# publicación programada y discreta (una vez al mes, en fecha conocida de
# antemano), no una serie que se actualiza a diario como DGS10 o FEDFUNDS:
# ahí "próxima actualización" no es un evento, es continuo.
RELEASE_IDS = dict(fred.RELEASE_IDS)


_parse_next_release_date = fred.parse_next_release_date

def fetch_next_release_date(series_id: str, api_key: str) -> date | None:
    """Próxima fecha de publicación programada (confirmada por la fuente
    oficial que FRED indexa, ej. BLS para CPI) -- None si `series_id` no
    tiene un release_id mapeado en RELEASE_IDS o si FRED no devuelve ninguna
    fecha futura."""
    return FredSource().next_release(series_id, api_key, date.today())


def get_snapshot() -> pd.DataFrame:
    return fred.snapshot(SERIES, {sid: get_series_history(sid) for sid in SERIES})
