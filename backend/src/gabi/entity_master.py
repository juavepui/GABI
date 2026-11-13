"""Entity Master: identidad de empresa con snapshots de sector/industria CON
fecha de efectividad, para poder responder "qué sector tenía esta empresa en
esta fecha" en vez de usar siempre el sector ACTUAL como hacía
`screener_asof.build_ranking_as_of` hasta ahora (look-ahead bias señalado
por el usuario: un sistema que se define point-in-time no debería rankear
una empresa de 2016 dentro de su sector de 2026).

No existe una fuente gratuita de sector HISTÓRICO. Lo único honesto que se
puede hacer es empezar a guardar, desde HOY, una foto con fecha cada vez que
se conoce el sector/industria/nombre de una empresa (`record_snapshot`,
enganchado a `screener.get_universe(force_refresh=True)`) para que dentro de
meses/años haya historial real. Para fechas anteriores a la primera foto
guardada (todo el histórico 2016-2025 actual) no hay point-in-time real —
`get_sector_asof` usa la foto más antigua disponible como aproximación,
marcada explícitamente (`is_approximate=True`) en vez de fingir que es un
dato point-in-time genuino.

La identidad persistente y los alias temporales viven en `identity.py`.
Los snapshots con CIK se atribuyen también a esa entidad. Las consultas
estrictas nunca cruzan entre compañías que reutilizan un ticker; la API
legacy se conserva para snapshots aún no migrados. Un snapshot fechado en
el pasado exige CIK explícito para acreditar identidad: el mapa SEC actual
no demuestra identidad histórica. Véase docs/entity-identity.md."""
import pandas as pd

from gabi.application.market import sector_snapshots as sector_queries
from gabi.infrastructure.storage import entity_snapshots as snapshot_storage

from . import edgar, identity

SCHEMA = snapshot_storage.SCHEMA


def record_snapshot(universe_df: pd.DataFrame, effective_date: str = None) -> int:
    """Guarda una foto de sector/industria/nombre para cada fila de
    `universe_df` (columnas symbol/name/sector/industry, tal y como devuelve
    `universe.get_sp500_constituents()`) con `effective_date` (por defecto
    hoy). Idempotente por (symbol, fecha): volver a llamar el mismo día
    sobrescribe en vez de duplicar. Resuelve el CIK vía
    `edgar.get_cik_for_symbol` — mejor esfuerzo, no falla si no resuelve
    (símbolo nuevo aún no indexado por la SEC, etc.). Devuelve cuántas filas
    se escribieron."""
    if universe_df.empty:
        return 0
    effective_date = effective_date or pd.Timestamp.today().date().isoformat()
    observed_today = effective_date == pd.Timestamp.today().date().isoformat()
    cik_map = edgar.get_cik_map() if observed_today else None
    rows = []
    attributed = []
    for _, row in universe_df.iterrows():
        symbol = row["symbol"]
        try:
            explicit_cik = row.get("cik")
            if explicit_cik is not None and pd.notna(explicit_cik):
                cik = identity.normalize_cik(explicit_cik)
            elif observed_today:
                cik, _title = edgar.get_cik_for_symbol(symbol, cik_map=cik_map)
            else:
                cik = None  # today's mapping cannot certify a backdated snapshot
        except Exception:
            cik = None
        rows.append((symbol, cik, row.get("name"), row.get("sector"), row.get("industry"), effective_date))
        if cik:
            entity_id = identity.import_filing_identity(symbol, cik, effective_date,
                                                        source="observed-universe-snapshot", name=row.get("name"))
            attributed.append((entity_id, symbol, {
                "name": row.get("name"), "sector": row.get("sector"), "industry": row.get("industry"),
                "cik": cik, "effective_date": effective_date,
            }))
    identity.sector_snapshots().record(rows, attributed)
    return len(rows)


def get_sector_asof(symbols: list, as_of_date: str, *, strict_identity: bool = False) -> dict:
    """{symbol: {"sector", "industry", "name", "cik", "effective_date",
    "is_approximate"}} en lote (el ranking la llama con el universo completo
    en cada periodo, igual que `edgar.get_last_filed_dates`).

    Para cada símbolo: usa la foto más reciente con `effective_date <=
    as_of_date` si existe (point-in-time real, `is_approximate=False`); si
    no, cae a la foto más antigua disponible como aproximación
    (`is_approximate=True`) — hoy en día, con solo una foto por símbolo
    tomada al implementar esto, esta rama es la que se usa para CUALQUIER
    fecha histórica, y da el mismo sector que el comportamiento anterior
    (sector actual). Símbolos sin ninguna foto (ej. deslistados antes de
    que existiera este mecanismo) devuelven sector=None, igual que antes."""
    return sector_queries.sector_as_of(identity, identity.sector_snapshots(), symbols, as_of_date, strict_identity=strict_identity)
