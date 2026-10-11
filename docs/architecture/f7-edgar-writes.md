# Escrituras EDGAR, resoluciones CIK y Company Facts por CIK (F7.16)

`edgar.py` deja de importar `storage`. Lo que quedaba de SQL legacy en la fachada
pasa a adaptadores ya usados por el worker:

| Antes en `edgar` | Ahora |
| --- | --- |
| `_CikCache` (CSV del mapa SEC) | `FileCikMap(CIK_CACHE)` |
| `_CikResolutions`, `_remember_cik_resolution`, `_get_cached_cik_resolution` | `SqliteCikResolutions(config.DB_PATH, reloj)` |
| `upsert_edgar_facts` | `identity.ensure_entity` + `SqliteXbrl.store_facts` |
| `upsert_edgar_metrics` | `SqliteXbrl.store_metrics` |
| `storage.record_update_errors("sec_edgar", …)` | `SqliteCacheWrites.update_errors` |

`SqliteXbrl` separa `FACTS_SCHEMA` y `METRICS_SCHEMA` (`SCHEMA` sigue siendo su
unión) y añade `store_facts`/`store_metrics` para las rutas que escriben uno
solo: descarga completa no incremental y Company Facts por CIK. Los hechos y su
atribución al emisor se confirman juntos; una atribución fallida revierte las
filas. Se conserva la entidad creada por `identity.ensure_entity` (fecha local),
la URL de procedencia y `fetched_at`.

En `sec_history`, `recover_companyfacts_gaps` e `ingest_issuer_companyfacts`
delegan en `application/research/sec_quarter_ingest.ingest_companyfacts`, con
`domain/market/sec_facts.issuer_companyfacts_rows` (CIK coincidente, conceptos
USD y acciones, ventana de presentación opcional). Se conservan los símbolos
`CIK##########`, los errores tratados por cada flujo (`KeyError` solo en el de
emisores), el informe reescrito tras cada CIK y sus mensajes.

## Efectos

- Las lecturas de resoluciones ya no crean la tabla; una base ausente devuelve
  `(None, None)`. Las resoluciones por lotes admiten 1.000 símbolos, el mismo
  tope que ya aplica la selección SEC.
- El mapa CIK se lee y escribe con límites (16 MiB, 50.000 filas) y reemplazo atómico.
- Inventario: `edgar` pierde `gabi.storage`. Siguen `identity` (resolución
  histórica y entidades) y `sync_state` (reintentos con el marcapasos único).

## Validación y medida

Referencia `c324aabadf3c7b517129f5cd55ffff880921d865` en
`fixtures/edgar_writes_migration.json`. `test_edgar_writes_migration.py` compara con
el código capturado: hechos con y sin CIK, revisiones, acciones y métricas;
reversión de atribución; resoluciones vivas, en caché y ausentes; mapa CIK
forzado y en caché con su checkpoint; errores de selección; y los dos flujos de
Company Facts con descarga caída, emisor equivocado, payload sin CIK y hechos
en el límite de la ventana. Tres mutaciones deliberadas (URL de procedencia,
límite de ventana y URL del informe) hacen fallar pruebas.
Validación del 2026-10-11: suite Python completa de 1.970 pruebas correcta.

Medida: `.venv/Scripts/python.exe scripts/measure_f7_edgar_writes.py`.
Windows/Python 3.13, 100 emisores con 60 hechos y métricas; filas idénticas.

| Flujo | Frío anterior → nuevo (s) | Mediana caliente (s) | Pico Python (MiB) |
| --- | --- | --- | --- |
| Hechos y métricas EDGAR | 1,4314 → 1,4105 | 1,2371 → 1,2760 | 0,04 → 0,04 |

Mismo coste: cada escritura sigue abriendo su conexión e inicializando su esquema.
