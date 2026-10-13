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
`domain.market.price_sync.yahoo_symbol`. `price_sync` usa `storage.database_path()`
porque `config` sería una dependencia legacy nueva. Inventario: `macro`, `insider` y
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

Pendiente de #134: los puentes de una sola ejecución `entity_migration`,
`historical_backfill` y `tenk_extraction` siguen con `storage.get_connection`;
los demás usos están en módulos de #131–#133.

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
