# Fuentes operativas sin la fachada storage (F7.19, #134)

Primera entrega de #134. Las fuentes operativas dejan de pasar por `storage`:

| Fachada | Ahora |
| --- | --- |
| `macro` (`upsert_series`, `get_series_history`, `get_all_fetched_at`, sincronización) | `SqliteFred`, el repositorio del worker; nueva lectura acotada `fetched_at_all` |
| `insider` (transacciones, `fetched_at`, errores, sincronización) | `SqliteInsiders` con el argumento opcional `database`, que conserva `config.DB_PATH` |
| `price_sync.run` | `domain/market/price_sync.py` (omisión, solape de 14 días, validación, cambio de ajuste, símbolo Yahoo) + `application/market/price_sync.py` + `SqliteCacheReads.adjusted_span`/`prices_from` + `SqliteCacheWrites` |
| `data_fetch` (precios, splits, fundamentales, cobertura, errores) | `cached_data` + `SqliteCacheWrites` |
| puente `data_health.identity` | `identity.name_candidates`, lectura acotada sin `ensure_schema` |

`price_sync` deja de importar `data_fetch` e `history_refresh`: desaparece el ciclo
`data_fetch`↔`price_sync`. `data_fetch.normalize_symbol` delega en
`domain.market.price_sync.yahoo_symbol`. En esta entrega `price_sync` usaba
`storage.database_path()`; la segunda la sustituye por `config` (ver abajo). Inventario: `macro`, `insider` y
`data_fetch` pierden `gabi.storage`; `price_sync` pierde `data_fetch.*`,
`history_refresh.*`, `numpy` y `pandas`.

## Contratos y efectos

- Mismas filas, `fetched_at`, checkpoints, eventos, motivos, descargas agrupadas y
  reparaciones de ajuste. El tamaño de la carga que se registra en cada intento
  (CSV de la respuesta) se inyecta desde la fachada.
- Las lecturas ya no crean esquema ni alteran `prices`; una tabla sin `adj_close`
  se lee como ausencia. Base ausente: resultados vacíos.
- Transacciones de insiders: lectura acotada a 10.000 filas por símbolo, con el
  mismo orden (más reciente primero); un exceso falla sin truncar.
- `macro.upsert_series` admite hasta 100.000 observaciones por escritura.
- La consulta de identidad de `data_health` ya no crea tablas al leer candidatos.

## Segunda entrega: ruta desde `config` y puentes sin `storage`

| Módulo | Ahora |
| --- | --- |
| `sync_state`, `price_sync` | `config.DB_PATH` leído por operación en lugar de `storage.database_path()` ([ADR 0005](../adr/0005-legacy-config-path.md)); `storage.database_path` se retira |
| puente `entity_migration` (`migrate`, `attribute_legacy`, `coverage_report`) | `infrastructure/storage/entity_migration.py`: instantáneas antiguas, atribución en una transacción y alias |
| puente `historical_backfill` (`run`, `fetch_missing_history`) | `infrastructure/storage/historical_backfill.py` (copia previa, cobertura antes/después, resumen del archivo, `quick_check`) + `SqliteCacheWrites` para precios y splits |
| puente `tenk_extraction.sample` | `SqliteIdentityAuditReads.issuer_candidates`, lectura acotada en solo lectura |

Las tres operaciones de los puentes son órdenes explícitas, así que conservan la
creación de esquema y la conexión WAL con espera de 30 s. Los candidatos del piloto
10-K se leen en solo lectura; sin la tabla, el error es `ValueError` en lugar de
`sqlite3.OperationalError`. Inventario: `sync_state` y `price_sync` cambian
`gabi.storage` por `gabi.config`; los puentes no figuran en él.

`storage.get_connection` queda sin usos de producción fuera de `storage`, salvo
`historical_revalidation`, `smallmid_feasibility` y `smallmid_test`, que #133 migra
junto con sus comandos de reproducción.

Validación: `test_bridge_storage_migration.py` con
`bridge_storage_migration.json` (código de `18bfcd87fc15b2e124ad6df76be2f1285b6d242e`).
Ejecuta el puente `entity_migration` capturado y el nuevo sobre bases temporales y
compara resultados y tablas; ejecuta los bloques SQL capturados de
`historical_backfill.run` y `tenk_extraction.sample` y compara sus resultados con
los adaptadores, la copia de seguridad y las escrituras de precios y splits. Una
mutación deliberada (quitar el filtro `adj_close IS NOT NULL`) hace fallar la prueba.
El acceso a datos no cambia: mismas consultas y una conexión por bloque, como antes.
Validación del 2026-10-14: suite Python completa de 2.092 pruebas correcta.

## Validación y medida

Fixtures: `price_sync_migration.json` y `operational_sources_migration.json`
(código de `c324aabadf3c7b517129f5cd55ffff880921d865`).
`test_price_sync_migration.py` recorre ocho pasos (carga inicial, sesión ya
consultada, solape, cambio solo de ajuste con reparación, full-refresh, datos
inválidos, error de descarga y respuesta que no es tabla) y compara resultados,
eventos, llamadas a Yahoo y tablas. `test_operational_sources_migration.py`
compara macro, insiders, lotes de `data_fetch` y candidatos por nombre. Cinco
mutaciones deliberadas (solape, ajuste, validación, metadatos FRED y orden de
insiders) hacen fallar pruebas. Validación del 2026-10-13: suite Python completa de
1.995 pruebas correcta.

Medida: `.venv/Scripts/python.exe scripts/measure_f7_price_sync.py`. Windows/Python
3.13, 100 símbolos y 528 sesiones sintéticas, Yahoo simulado; filas idénticas.

| Flujo | Anterior (s) | Nuevo (s) |
| --- | --- | --- |
| Primera carga | 5,7409 | 4,1271 |
| Sesión ya consultada (mediana de 3) | 1,3010 | 1,1369 |

El ahorro procede de no inicializar esquema en cada lectura; son tiempos de esta fixture.
