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
import hashlib
import json
from datetime import UTC, datetime

import pandas as pd

from gabi.application.administration import data_quality as quality_queries
from gabi.domain.market import data_quality as quality

from . import config, edgar, entity_master, insider, macro, scoring, storage

PRICE_STALE_DAYS = quality.PRICE_STALE_DAYS
STRUCTURAL_LIMITATIONS = list(quality.STRUCTURAL_LIMITATIONS)


def _age_hours(fetched_at):
    return quality.age_hours(fetched_at, now=datetime.now(UTC))


def local_cik_status(symbols: list) -> dict:
    """Resuelve únicamente contra archivos/tablas locales, sin refrescar ni escribir."""
    result = dict.fromkeys(symbols)
    with storage.get_connection() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='cik_resolutions'").fetchone()
        if exists:
            for symbol, cik in conn.execute("SELECT symbol, cik FROM cik_resolutions"):
                if symbol in result:
                    result[symbol] = cik
    if edgar.CIK_CACHE.exists():
        frame = pd.read_csv(edgar.CIK_CACHE, dtype={"cik": str})
        mapping = dict(zip(frame["symbol"], frame["cik"], strict=True))
        for symbol in symbols:
            result[symbol] = mapping.get(symbol, mapping.get(symbol.replace(".", "-"), result[symbol]))
    return result


def _fetched_at_summary(label, symbols, fetched_map, threshold_hours):
    return quality.fetched_at_summary(label, symbols, fetched_map, threshold_hours, now=datetime.now(UTC))


def _readers():
    return quality_queries.QualityReaders(
        storage.get_price_coverage, storage.get_fundamentals_fetched_at,
        edgar.get_edgar_fetched_at, insider.get_insider_fetched_at, edgar.get_symbols_with_facts,
        entity_master.get_sector_asof, local_cik_status, edgar.CIK_CACHE.exists(),
        macro.get_all_fetched_at, tuple(macro.SERIES), macro.get_series_history,
        storage.get_fundamentals, edgar.get_edgar_metrics)


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
    días) de cualquier fuente -- ver `storage.record_update_errors`."""
    return storage.get_recent_update_errors(since_hours=since_hours)


def compute_data_fingerprint(symbols: list | None = None, *, inputs: dict | None = None) -> str:
    """SHA-256 v2 del contenido local, en una transacción de lectura coherente.

    Incluye precios (también benchmark), splits, XBRL, fundamentales, sectores,
    CIK, FRED y composición del universo. None incluye todos los símbolos.
    El llamador debe capturarlo al ejecutar, y conservarlo con el resultado.
    Identifica una caché: no conserva por sí solo una copia recuperable de ella.
    """
    selected = None if symbols is None else sorted(set(symbols) | {config.BENCHMARK_SYMBOL})
    digest = hashlib.sha256()

    def feed(value):
        digest.update(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), default=str).encode("utf-8"))
        digest.update(b"\n")

    feed({"version": 2, "symbols": selected, "inputs": inputs or {}})
    tables = ("prices", "splits", "fundamentals", "edgar_metrics", "edgar_facts",
              "entity_snapshots", "cik_resolutions", "macro_series", "macro_meta",
              "entities", "entity_aliases", "entity_observations", "entity_candidates")
    with storage.get_connection() as conn:
        conn.execute("BEGIN")
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in tables:
            feed(table)
            if table not in existing:
                continue
            columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
            # Download times do not change the actual financial input.
            columns = [c for c in columns if c not in {"fetched_at", "resolved_at"}]
            feed(columns)
            fields = ",".join(f'"{c}"' for c in columns)
            query = f'SELECT {fields} FROM "{table}"'
            params = []
            if selected is not None and "symbol" in columns and not table.startswith("entit"):
                query += " WHERE symbol IN (" + ",".join("?" for _ in selected) + ")"
                params = selected
            query += " ORDER BY " + fields
            for row in conn.execute(query, params):
                feed([json.loads(value) if column.endswith("_json") and value else value
                      for column, value in zip(columns, row, strict=True)])
    for name in ("sp500_constituents.csv", "sp500_historical_membership.csv", "sec_cik_map.csv"):
        path = config.DATA_DIR / name
        feed(name)
        if path.exists():
            frame = pd.read_csv(path, dtype=str).fillna("")
            columns = sorted(frame.columns)
            feed(columns)
            for row in sorted(frame[columns].itertuples(index=False, name=None)):
                feed(row)
    return "v2:" + digest.hexdigest()


DEFAULT_DEGRADED_BLOCK_THRESHOLD = quality.DEFAULT_DEGRADED_BLOCK_THRESHOLD
DEFAULT_CONFIDENCE_THRESHOLD = quality.DEFAULT_CONFIDENCE_THRESHOLD


def ranking_quality(df):
    return quality.ranking_quality(df, metrics=tuple((block, tuple(cols)) for block, cols in scoring.SCORE_METRICS.items()))


ranking_quality_warnings = quality.ranking_quality_warnings
block_coverage_warnings = quality.block_coverage_warnings
low_confidence_candidates = quality.low_confidence_candidates
