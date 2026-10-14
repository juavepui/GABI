"""Observabilidad de datos: calidad, frescura y procedencia de todo lo que
GABI cachea localmente -- para poder responder no solo qué score produce un
símbolo, sino con qué calidad, frescura y procedencia se calculó.

Cada fuente (precios, fundamentales Yahoo, SEC EDGAR, insider Form 4, FRED
macro, Entity Master) ya llevaba su propio `fetched_at`/`max_age_hours` por
separado, repartido en `storage.py`, `data_fetch.py`, `edgar.py`,
`insider.py`, `macro.py` y `entity_master.py` -- no había un sitio único
donde ver "qué calidad tienen mis datos" (agregado, por universo) ni "de
dónde procede este resultado" (desglosado, por empresa). Este módulo solo
agrega lo que ya existe: no añade ninguna fuente, umbral ni llamada de red
nueva -- todo se lee de la caché local (SQLite/CSV), nunca dispara un
fetch, así que es seguro de usar en tests."""
from datetime import UTC, datetime

import pandas as pd

from gabi.application.administration import data_quality as quality_queries
from gabi.application.market import cached_data
from gabi.domain.market import data_quality as quality
from gabi.domain.market import fred
from gabi.infrastructure.storage import data_fingerprint
from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
from gabi.infrastructure.storage.fred import SqliteFred
from gabi.infrastructure.storage.insiders import SqliteInsiders
from gabi.infrastructure.storage.sec_cik import SqliteCikResolutions

from . import config, edgar, entity_master, scoring

PRICE_STALE_DAYS = quality.PRICE_STALE_DAYS
STRUCTURAL_LIMITATIONS = list(quality.STRUCTURAL_LIMITATIONS)


def _age_hours(fetched_at):
    return quality.age_hours(fetched_at, now=datetime.now(UTC))


def local_cik_status(symbols: list) -> dict:
    """Resuelve únicamente contra archivos/tablas locales, sin refrescar ni escribir."""
    result = dict.fromkeys(symbols)
    resolutions = SqliteCikResolutions(config.DB_PATH, lambda: datetime.now(UTC))
    unique = list(result)
    for start in range(0, len(unique), 1000):
        for symbol, (cik, _title) in resolutions.cached_many(unique[start:start + 1000]).items():
            result[symbol] = cik
    if edgar.CIK_CACHE.exists():
        frame = pd.read_csv(edgar.CIK_CACHE, dtype={"cik": str})
        mapping = dict(zip(frame["symbol"], frame["cik"], strict=True))
        for symbol in symbols:
            result[symbol] = mapping.get(symbol, mapping.get(symbol.replace(".", "-"), result[symbol]))
    return result


def _fetched_at_summary(label, symbols, fetched_map, threshold_hours):
    return quality.fetched_at_summary(label, symbols, fetched_map, threshold_hours, now=datetime.now(UTC))


def _cache():
    # The compatibility setting is captured per operation, never mutated.
    return SqliteCacheReads(config.DB_PATH)


def _readers():
    # Read-only: the stores' clocks only stamp writes.
    insiders = SqliteInsiders(config.DB_PATH.parent, database=config.DB_PATH)
    macro = SqliteFred(config.DB_PATH, lambda: datetime.now(UTC))
    return quality_queries.QualityReaders(
        lambda symbols: cached_data.price_coverage(_cache(), symbols),
        lambda symbols: cached_data.fundamentals_fetched_at(_cache(), symbols),
        edgar.get_edgar_fetched_at, insiders.fetched_at, edgar.get_symbols_with_facts,
        entity_master.get_sector_asof, local_cik_status, edgar.CIK_CACHE.exists(),
        macro.fetched_at_all, tuple(fred.SERIES), macro.history,
        lambda symbols: cached_data.fundamentals(_cache(), symbols), edgar.get_edgar_metrics)


def _rules():
    return quality.QualityRules(config.CACHE_MAX_AGE_HOURS, config.EDGAR_CACHE_MAX_AGE_HOURS,
                                PRICE_STALE_DAYS, tuple(STRUCTURAL_LIMITATIONS))


def universe_summary(symbols):
    return quality_queries.summary(symbols, _readers(), now=datetime.now(UTC), rules=_rules())


def symbol_provenance(symbol, as_of=None):
    return quality_queries.provenance(symbol, _readers(), now=datetime.now(UTC), as_of=as_of, rules=_rules())


def score_block_coverage(df):
    return quality.score_block_coverage(df, metrics=tuple((block, tuple(cols)) for block, cols in scoring.SCORE_METRICS.items()))


def recent_errors_summary(since_hours: float = 24 * 7) -> pd.DataFrame:
    """Fallos de actualización de los últimos `since_hours` (por defecto, 7
    días) de cualquier fuente -- ver `SqliteCacheWrites.update_errors`."""
    return cached_data.recent_update_errors(_cache(), now=datetime.now(UTC), since_hours=since_hours)


def compute_data_fingerprint(symbols: list | None = None, *, inputs: dict | None = None) -> str:
    """SHA-256 v2 del contenido local, en una transacción de lectura coherente.

    Incluye precios (también benchmark), splits, XBRL, fundamentales, sectores,
    CIK, FRED y composición del universo. None incluye todos los símbolos.
    El llamador debe capturarlo al ejecutar, y conservarlo con el resultado.
    Identifica una caché: no conserva por sí solo una copia recuperable de ella.
    """
    selected = None if symbols is None else sorted(set(symbols) | {config.BENCHMARK_SYMBOL})
    return data_fingerprint.fingerprint(config.DB_PATH, config.DATA_DIR, selected, inputs or {})


DEFAULT_DEGRADED_BLOCK_THRESHOLD = quality.DEFAULT_DEGRADED_BLOCK_THRESHOLD
DEFAULT_CONFIDENCE_THRESHOLD = quality.DEFAULT_CONFIDENCE_THRESHOLD


def ranking_quality(df):
    return quality.ranking_quality(df, metrics=tuple((block, tuple(cols)) for block, cols in scoring.SCORE_METRICS.items()))


ranking_quality_warnings = quality.ranking_quality_warnings
block_coverage_warnings = quality.block_coverage_warnings
low_confidence_candidates = quality.low_confidence_candidates
